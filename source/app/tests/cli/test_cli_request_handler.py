# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import json
import re
from datetime import date
from typing import Any, Iterator, Optional, Sequence
from unittest.mock import patch

from _pytest.fixtures import fixture
from packaging.version import Version

from instance_scheduler import __version__
from instance_scheduler.handler.cli.cli_request_handler import (
    CliRequestHandler,
    get_supported_cli_versions,
)
from instance_scheduler.handler.environments.main_lambda_environment import (
    MainLambdaEnv,
)
from instance_scheduler.model.period_definition import PeriodDefinition
from instance_scheduler.model.period_identifier import PeriodIdentifier
from instance_scheduler.model.schedule_definition import ScheduleDefinition
from instance_scheduler.model.store.period_definition_store import PeriodDefinitionStore
from instance_scheduler.model.store.schedule_definition_store import (
    ScheduleDefinitionStore,
)
from instance_scheduler.util.dynamodb_utils import DynamoDBUtils
from tests.context import MockLambdaContext
from tests.logger import MockLogger
from tests.test_utils.mock_main_lambda_env import MockMainLambdaEnv
from tests.test_utils.unordered_list import UnorderedList


@fixture(autouse=True)
def mock_logger() -> Iterator[None]:
    with patch("instance_scheduler.handler.cli.cli_request_handler.Logger", MockLogger):
        yield


def test_is_handling_request() -> None:
    assert CliRequestHandler.is_handling_request(
        {"source": "scheduler.cli", "action": "something"}
    )

    assert not CliRequestHandler.is_handling_request(
        {"source": "anything.else", "action": "another_thing"}
    )


def test_cli_receives_successful_response_with_supported_cli_version(
    config_table: None,
) -> None:
    result = describe_schedules_with_cli(version=__version__)
    assert "Schedules" in result


def test_get_supported_cli_versions_is_human_readable() -> None:
    # matches version pattern (optional range) like x.x.x or x.x.x-x.x.x
    assert re.match(r"^\d+\.\d+\.\d+(-\d+\.\d+\.\d+)?$", get_supported_cli_versions())


def test_cli_receives_error_response_with_old_cli_version() -> None:
    result = describe_schedules_with_cli(version="0.0.0")
    assert result == {
        "Error": f"CLI version 0.0.0 is not supported for this version of the solution. Please update to a supported version ({get_supported_cli_versions()})."
    }


def test_cli_receives_error_response_with_new_cli_version() -> None:
    result = describe_schedules_with_cli(version="100.0.0")
    assert result == {
        "Error": f"CLI version 100.0.0 is not supported for this version of the solution. Please update to a supported version ({get_supported_cli_versions()})."
    }


def test_cli_success_with_cli_on_same_minor_version_but_greater_patch(
    config_table: None,
) -> None:
    cli_version = Version(__version__)
    greater_patch_version = (
        f"{cli_version.major}.{cli_version.minor}.{cli_version.micro + 1}"
    )
    result = describe_schedules_with_cli(version=greater_patch_version)
    assert "Schedules" in result


def test_cli_success_with_cli_on_same_minor_version_but_smaller_patch(
    config_table: None,
) -> None:
    cli_version = Version(__version__)
    minor_version = cli_version.micro - 1 if cli_version.micro > 0 else 0
    lower_patch_version = f"{cli_version.major}.{cli_version.minor}.{minor_version}"
    result = describe_schedules_with_cli(version=lower_patch_version)
    assert "Schedules" in result


def test_create_schedule_throws_error_when_period_not_found(config_table: None) -> None:
    result = create_schedule_with_cli(periods=["office-hours"])
    assert result == {"Error": "error: not found: period office-hours does not exist"}


def test_create_schedule_with_2_periods(
    config_table: None, test_suite_env: MainLambdaEnv
) -> None:
    create_period_with_cli(name="period1")
    create_period_with_cli(name="period2")

    result = create_schedule_with_cli(
        periods=["period1", "period2"], name="cli-schedule"
    )

    assert result == {
        "Schedule": {
            "Name": "cli-schedule",
            "Periods": UnorderedList(["period1", "period2"]),
            "StopNewInstances": True,
            "RetainRunning": False,
            "Enforced": False,
            "Hibernate": False,
            "Type": "schedule",
            "UseMaintenanceWindow": True,
        }
    }

    created_schedule = get_schedule_from_dynamo("cli-schedule", test_suite_env)
    assert created_schedule == {
        "type": "schedule",
        "name": "cli-schedule",
        "periods": {"period1", "period2"},
        "stop_new_instances": True,
        "retain_running": False,
        "enforced": False,
        "hibernate": False,
        "use_maintenance_window": True,
    }


def test_create_schedule_with_2_maintenance_windows(
    config_table: None, test_suite_env: MainLambdaEnv
) -> None:
    create_period_with_cli(name="period")

    result = create_schedule_with_cli(
        name="cli-schedule",
        periods=["period"],
        ssm_maintenance_window=["window1", "window2"],
        use_maintenance_window=True,
    )

    assert result == {
        "Schedule": {
            "Name": "cli-schedule",
            "Periods": ["period"],
            "StopNewInstances": True,
            "SsmMaintenanceWindow": UnorderedList(["window1", "window2"]),
            "UseMaintenanceWindow": True,
            "RetainRunning": False,
            "Enforced": False,
            "Hibernate": False,
            "Type": "schedule",
        }
    }

    created_schedule = get_schedule_from_dynamo("cli-schedule", test_suite_env)
    assert created_schedule == {
        "type": "schedule",
        "name": "cli-schedule",
        "periods": {"period"},
        "stop_new_instances": True,
        "ssm_maintenance_window": {"window1", "window2"},
        "use_maintenance_window": True,
        "retain_running": False,
        "enforced": False,
        "hibernate": False,
    }


def test_create_schedule_throws_error_when_schedule_already_exists(
    config_table: None,
) -> None:
    create_period_with_cli(name="period1")
    create_schedule_with_cli(name="cli-schedule", periods=["period1"])
    result = create_schedule_with_cli(name="cli-schedule", periods=["period1"])

    assert result == {"Error": "error: schedule cli-schedule already exists"}


def test_delete_existing_schedule(
    config_table: None, test_suite_env: MainLambdaEnv
) -> None:
    create_period_with_cli(name="period1")
    create_period_with_cli(name="period2")
    create_schedule_with_cli(periods=["period1", "period2"], name="cli-schedule")

    assert get_schedule_from_dynamo("cli-schedule", test_suite_env) is not None
    result = delete_schedule_with_cli("cli-schedule")
    assert result == {"Schedule": "cli-schedule"}
    assert get_schedule_from_dynamo("cli-schedule", test_suite_env) is None


def test_delete_schedule_will_not_delete_cfn_managed_schedule(
    schedule_store: ScheduleDefinitionStore,
) -> None:
    schedule_store.put(
        ScheduleDefinition(
            name="test-schedule",
            periods=[PeriodIdentifier.of("test-period")],
            configured_in_stack="myStackArn",
        )
    )

    result = delete_schedule_with_cli("test-schedule")
    assert result == {
        "Error": "Schedule test-schedule is owned by myStackArn and cannot be deleted by the cli. "
        "Please delete the owning stack to delete this schedule"
    }
    assert schedule_store.find_by_name("test-schedule") is not None


def test_delete_nonexisting_schedule_returns_error(config_table: None) -> None:
    result = delete_schedule_with_cli("cli-schedule")
    assert result == {"Error": "not found: schedule cli-schedule does not exist"}


def test_create_basic_period(config_table: None, test_suite_env: MainLambdaEnv) -> None:
    result = create_period_with_cli(
        name="cli-period", begintime="10:00", endtime="20:00"
    )

    assert result == {
        "Period": {
            "Begintime": "10:00",
            "Endtime": "20:00",
            "Name": "cli-period",
            "Type": "period",
        }
    }

    created_period = get_period_from_dynamo(name="cli-period", app_env=test_suite_env)
    assert created_period == {
        "type": "period",
        "name": "cli-period",
        "begintime": "10:00",
        "endtime": "20:00",
    }


def test_create_complex_period(
    config_table: None, test_suite_env: MainLambdaEnv
) -> None:
    result = create_period_with_cli(
        name="cli-period",
        begintime="10:00",
        endtime="20:00",
        weekdays="mon",
        monthdays="1-5",
        months="1",
    )

    assert result == {
        "Period": {
            "Begintime": "10:00",
            "Endtime": "20:00",
            "Name": "cli-period",
            "Type": "period",
            "Monthdays": ["1-5"],
            "Months": ["1"],
            "Weekdays": ["mon"],
        }
    }

    created_period = get_period_from_dynamo(name="cli-period", app_env=test_suite_env)
    assert created_period == {
        "type": "period",
        "name": "cli-period",
        "begintime": "10:00",
        "endtime": "20:00",
        "monthdays": {"1-5"},
        "months": {"1"},
        "weekdays": {"mon"},
    }


def test_create_period_throws_error_when_period_already_exists(
    config_table: None,
) -> None:
    create_period_with_cli(name="cli-period")
    result = create_period_with_cli(name="cli-period")

    assert result == {"Error": "error: period cli-period already exists"}


def test_delete_existing_period(
    config_table: None, test_suite_env: MainLambdaEnv
) -> None:
    create_period_with_cli(name="cli-period")

    assert get_period_from_dynamo("cli-period", test_suite_env) is not None
    result = delete_period_with_cli("cli-period")
    assert result == {"Period": "cli-period"}
    assert get_period_from_dynamo("cli-period", test_suite_env) is None


def test_delete_nonexisting_period_returns_error(config_table: None) -> None:
    result = delete_period_with_cli("cli-period")
    assert result == {"Error": "not found: period cli-period does not exist"}


def test_delete_period_returns_error_if_period_is_used_by_a_schedule(
    config_table: None,
) -> None:
    create_period_with_cli(name="cli-period")
    create_schedule_with_cli(name="cli-schedule", periods=["cli-period"])

    result = delete_period_with_cli("cli-period")
    assert result == {
        "Error": "error: period cli-period can not be deleted because it is still used in schedule(s) ['cli-schedule']"
    }


def test_delete_period_will_not_delete_cfn_managed_period(
    period_store: PeriodDefinitionStore,
) -> None:
    period_store.put(
        PeriodDefinition(
            name="test-period",
            begintime="5:00",
            endtime="10:00",
            configured_in_stack="myStackArn",
        )
    )

    result = delete_period_with_cli("test-period")
    assert result == {
        "Error": "Period test-period is owned by myStackArn and cannot be deleted by the cli. "
        "Please delete the owning stack to delete this period"
    }
    assert period_store.find_by_name("test-period") is not None


def test_describe_all_periods_is_empty_when_no_periods_created(
    config_table: None,
) -> None:
    result = describe_periods_with_cli()
    assert result == {"Periods": []}


def test_describe_all_periods_returns_created_periods(config_table: None) -> None:
    create_period_with_cli("period1", begintime="05:00", endtime="10:00"),
    create_period_with_cli("period2", begintime="12:00", endtime="14:00")
    result = describe_periods_with_cli()
    assert result == {
        "Periods": UnorderedList(
            [
                {
                    "Type": "period",
                    "Name": "period1",
                    "Begintime": "05:00",
                    "Endtime": "10:00",
                },
                {
                    "Type": "period",
                    "Name": "period2",
                    "Begintime": "12:00",
                    "Endtime": "14:00",
                },
            ]
        )
    }


def test_describe_periods_handles_sets_correctly(
    period_store: PeriodDefinitionStore,
) -> None:
    period_store.put(PeriodDefinition(name="test-period", weekdays={"1", "3", "5-6"}))

    result = describe_periods_with_cli("test-period")
    assert result == {
        "Periods": UnorderedList(
            [
                {
                    "Type": "period",
                    "Name": "test-period",
                    "Weekdays": UnorderedList(["1", "3", "5-6"]),
                },
            ]
        )
    }


def test_describe_specific_period_returns_expected_period(config_table: None) -> None:
    create_period_with_cli("period1", begintime="05:00", endtime="10:00"),
    create_period_with_cli("period2", begintime="12:00", endtime="14:00")
    result = describe_periods_with_cli("period1")
    assert result == {
        "Periods": UnorderedList(
            [
                {
                    "Type": "period",
                    "Name": "period1",
                    "Begintime": "05:00",
                    "Endtime": "10:00",
                },
            ]
        )
    }


def test_describe_specific_period_returns_error_when_not_exists(
    config_table: None,
) -> None:
    create_period_with_cli("period1", begintime="05:00", endtime="10:00"),
    create_period_with_cli("period2", begintime="12:00", endtime="14:00")
    result = describe_periods_with_cli("period3")
    assert result == {"Error": "not found: period period3 does not exist"}


def test_describe_all_schedules_is_empty_when_no_schedules_created(
    config_table: None,
) -> None:
    result = describe_schedules_with_cli()
    assert result == {"Schedules": []}


def test_describe_all_schedules_returns_created_schedules(config_table: None) -> None:
    create_period_with_cli("period1", begintime="05:00", endtime="10:00"),
    create_period_with_cli("period2", begintime="12:00", endtime="14:00")
    create_schedule_with_cli(
        periods=["period1"], name="schedule1", stop_new_instances=False
    )
    create_schedule_with_cli(
        periods=["period2"],
        name="schedule2",
        retain_running=True,
        use_maintenance_window=False,
    )

    result = describe_schedules_with_cli()
    assert result == {
        "Schedules": UnorderedList(
            [
                {
                    "Type": "schedule",
                    "Name": "schedule1",
                    "Periods": ["period1"],
                    "StopNewInstances": False,
                    "RetainRunning": False,
                    "Enforced": False,
                    "Hibernate": False,
                    "UseMaintenanceWindow": True,
                },
                {
                    "Type": "schedule",
                    "Name": "schedule2",
                    "Periods": ["period2"],
                    "StopNewInstances": True,
                    "RetainRunning": True,
                    "Enforced": False,
                    "Hibernate": False,
                    "UseMaintenanceWindow": False,
                },
            ]
        )
    }


def test_describe_specific_schedule_returns_expected_schedule(
    config_table: None,
) -> None:
    create_period_with_cli("period1", begintime="05:00", endtime="10:00"),
    create_period_with_cli("period2", begintime="12:00", endtime="14:00")
    create_schedule_with_cli(
        periods=["period1"],
        name="schedule1",
        ssm_maintenance_window=["window"],
    )
    create_schedule_with_cli(periods=["period2"], name="schedule2", enforced=True)

    result = describe_schedules_with_cli("schedule1")
    assert result == {
        "Schedules": [
            {
                "Type": "schedule",
                "Name": "schedule1",
                "Periods": ["period1"],
                "StopNewInstances": True,
                "SsmMaintenanceWindow": ["window"],
                "RetainRunning": False,
                "Enforced": False,
                "Hibernate": False,
                "UseMaintenanceWindow": True,
            },
        ]
    }


def test_describe_specific_schedule_returns_error_when_not_exists(
    config_table: None,
) -> None:
    create_period_with_cli("period1", begintime="05:00", endtime="10:00"),
    create_period_with_cli("period2", begintime="12:00", endtime="14:00")
    create_schedule_with_cli(
        periods=["period1"],
        name="schedule1",
        ssm_maintenance_window=["window"],
    )
    create_schedule_with_cli(periods=["period2"], name="schedule2", enforced=True)

    result = describe_schedules_with_cli("schedule3")
    assert result == {"Error": "not found: schedule schedule3 does not exist"}


def test_describe_schedule_usage(config_table: None) -> None:
    create_period_with_cli("cli-period", begintime="09:00", endtime="17:00"),
    create_schedule_with_cli(periods=["cli-period"], name="cli-schedule")
    result = describe_schedule_usage_with_cli(
        "cli-schedule", startdate=date(2023, 7, 20), enddate=date(2023, 7, 21)
    )
    assert result == {
        "Schedule": "cli-schedule",
        "Usage": {
            "2023-07-20": {
                "BillingHours": 8,
                "BillingSeconds": 28800,
                "RunningPeriods": {
                    "Cli-period": {
                        "Begin": "07/20/23 09:00:00",
                        "BillingHours": 8,
                        "BillingSeconds": 28800,
                        "End": "07/20/23 17:00:00",
                    }
                },
            },
            "2023-07-21": {
                "BillingHours": 8,
                "BillingSeconds": 28800,
                "RunningPeriods": {
                    "Cli-period": {
                        "Begin": "07/21/23 09:00:00",
                        "BillingHours": 8,
                        "BillingSeconds": 28800,
                        "End": "07/21/23 17:00:00",
                    }
                },
            },
        },
    }


def test_update_period(config_table: None, test_suite_env: MainLambdaEnv) -> None:
    create_period_with_cli("cli-period", begintime="02:00", endtime="4:00")
    result = update_period_with_cli("cli-period", begintime="12:00", endtime="15:00")

    assert result == {
        "Period": {
            "Begintime": "12:00",
            "Endtime": "15:00",
            "Name": "cli-period",
            "Type": "period",
        }
    }

    updated_period = get_period_from_dynamo("cli-period", test_suite_env)
    assert updated_period == {
        "type": "period",
        "name": "cli-period",
        "begintime": "12:00",
        "endtime": "15:00",
    }


def test_update_period_returns_error_when_period_managed_by_cfn(
    period_store: PeriodDefinitionStore,
) -> None:
    orig_period = PeriodDefinition(
        name="test-period",
        begintime="10:00",
        configured_in_stack="myStackArn",
    )
    period_store.put(orig_period)

    result = update_period_with_cli(name="test-period", begintime="12:00")
    assert result == {
        "Error": "Period test-period is owned by myStackArn and cannot be edited by the cli. "
        "Please update the owning stack to edit this period"
    }
    assert period_store.find_by_name("test-period") == orig_period


def test_update_period_returns_error_when_period_does_not_exist(
    config_table: None,
) -> None:
    result = update_period_with_cli("cli-period", begintime="12:00", endtime="15:00")

    assert result == {"Error": "not found: period cli-period does not exist"}


def test_update_schedule(config_table: None, test_suite_env: MainLambdaEnv) -> None:
    create_period_with_cli("period1")
    create_period_with_cli("period2")
    create_schedule_with_cli(
        periods=["period1"], name="cli-schedule", retain_running=True
    )

    result = update_schedule_with_cli(
        name="cli-schedule",
        periods=["period1", "period2"],
        retain_running=False,
        enforced=True,
    )

    assert result == {
        "Schedule": {
            "Name": "cli-schedule",
            "Periods": UnorderedList(["period1", "period2"]),
            "StopNewInstances": True,
            "RetainRunning": False,
            "Enforced": True,
            "Hibernate": False,
            "Type": "schedule",
        }
    }

    updated_schedule = get_schedule_from_dynamo("cli-schedule", test_suite_env)
    assert updated_schedule == {
        "type": "schedule",
        "name": "cli-schedule",
        "periods": {"period1", "period2"},
        "stop_new_instances": True,
        "retain_running": False,
        "enforced": True,
        "hibernate": False,
    }


def test_update_schedule_with_2_maintenance_windows(
    config_table: None, test_suite_env: MainLambdaEnv
) -> None:
    create_period_with_cli("period")
    create_schedule_with_cli(
        periods=["period"], name="cli-schedule", retain_running=True
    )

    result = update_schedule_with_cli(
        name="cli-schedule",
        periods=["period"],
        retain_running=False,
        enforced=True,
        ssm_maintenance_window=["window1", "window2"],
    )

    assert result == {
        "Schedule": {
            "Name": "cli-schedule",
            "Periods": ["period"],
            "StopNewInstances": True,
            "SsmMaintenanceWindow": UnorderedList(["window1", "window2"]),
            "RetainRunning": False,
            "Enforced": True,
            "Hibernate": False,
            "Type": "schedule",
        }
    }

    updated_schedule = get_schedule_from_dynamo("cli-schedule", test_suite_env)
    assert updated_schedule == {
        "type": "schedule",
        "name": "cli-schedule",
        "periods": {"period"},
        "stop_new_instances": True,
        "ssm_maintenance_window": {"window1", "window2"},
        "retain_running": False,
        "enforced": True,
        "hibernate": False,
    }


def test_update_schedule_returns_error_when_schedule_does_not_exist(
    config_table: None,
) -> None:
    create_period_with_cli("period1")
    result = update_schedule_with_cli(name="cli-schedule", periods=["period1"])

    assert result == {"Error": "not found: schedule cli-schedule does not exist"}


def test_update_schedule_returns_error_when_schedule_managed_by_cfn(
    schedule_store: ScheduleDefinitionStore, period_store: PeriodDefinitionStore
) -> None:
    # needed because cli checks if period exists
    period_store.put(PeriodDefinition(name="period", begintime="10:00"))
    orig_sched = ScheduleDefinition(
        name="test-schedule",
        periods=[PeriodIdentifier.of("test-period")],
        configured_in_stack="myStackArn",
    )
    schedule_store.put(orig_sched)

    result = update_schedule_with_cli(
        name="test-schedule",
        periods=["period"],
    )

    assert result == {
        "Error": "Schedule test-schedule is owned by myStackArn and cannot be edited by the cli. "
        "Please update the owning stack to edit this schedule"
    }
    assert schedule_store.find_by_name("test-schedule") == orig_sched


def test_update_schedule_returns_error_when_period_does_not_exist(
    config_table: None,
) -> None:
    result = update_schedule_with_cli(name="cli-schedule", periods=["period1"])

    assert result == {"Error": "error: not found: period period1 does not exist"}


# ------------------------------Begin Helpers------------------------------ #


def is_valid_json(json_data: Any) -> bool:
    json.dumps(json_data)
    return True


def create_period_with_cli(
    name: str = "cli-period",
    begintime: str = "10:00",
    endtime: str = "20:00",
    weekdays: Optional[str] = None,
    monthdays: Optional[str] = None,
    months: Optional[str] = None,
    version: str = __version__,
) -> Any:
    parameters = {"name": name, "begintime": begintime, "endtime": endtime}

    if weekdays:
        parameters["weekdays"] = weekdays
    if monthdays:
        parameters["monthdays"] = monthdays
    if months:
        parameters["months"] = months

    event = {
        "source": "scheduler.cli",
        "action": "create-period",
        "parameters": parameters,
        "version": version,
    }

    handler = CliRequestHandler(event, MockLambdaContext(), MockMainLambdaEnv())
    result = handler.handle_request()
    assert is_valid_json(result)
    return result


def update_period_with_cli(
    name: str = "cli-period",
    begintime: str = "10:00",
    endtime: str = "20:00",
    version: str = __version__,
) -> Any:
    event = {
        "source": "scheduler.cli",
        "action": "update-period",
        "parameters": {"name": name, "begintime": begintime, "endtime": endtime},
        "version": version,
    }

    handler = CliRequestHandler(event, MockLambdaContext(), MockMainLambdaEnv())
    result = handler.handle_request()
    assert is_valid_json(result)
    return result


def delete_period_with_cli(
    name: str,
    version: str = __version__,
) -> Any:
    event = {
        "source": "scheduler.cli",
        "action": "delete-period",
        "parameters": {"name": name},
        "version": version,
    }
    handler = CliRequestHandler(event, MockLambdaContext(), MockMainLambdaEnv())
    result = handler.handle_request()
    assert is_valid_json(result)
    return result


def create_schedule_with_cli(
    periods: Sequence[str],
    name: str = "cli-schedule",
    stop_new_instances: bool = True,
    retain_running: bool = False,
    enforced: bool = False,
    hibernate: bool = False,
    ssm_maintenance_window: Optional[Sequence[str]] = None,
    use_maintenance_window: Optional[bool] = True,
    version: str = __version__,
) -> Any:
    event: dict[str, Any] = {
        "source": "scheduler.cli",
        "action": "create-schedule",
        "parameters": {
            "name": name,
            "periods": ",".join(periods),
            "stop_new_instances": stop_new_instances,
            "retain_running": retain_running,
            "enforced": enforced,
            "hibernate": hibernate,
            "use_maintenance_window": use_maintenance_window,
        },
        "version": version,
    }

    if ssm_maintenance_window:
        event["parameters"]["ssm_maintenance_window"] = ssm_maintenance_window

    handler = CliRequestHandler(event, MockLambdaContext(), MockMainLambdaEnv())
    result = handler.handle_request()
    assert is_valid_json(result)
    return result


def update_schedule_with_cli(
    periods: Sequence[str],
    name: str = "cli-schedule",
    stop_new_instances: bool = True,
    retain_running: bool = False,
    enforced: bool = False,
    hibernate: bool = False,
    ssm_maintenance_window: Optional[Sequence[str]] = None,
    version: str = __version__,
) -> Any:
    event: dict[str, Any] = {
        "source": "scheduler.cli",
        "action": "update-schedule",
        "parameters": {
            "name": name,
            "periods": ",".join(periods),
            "stop_new_instances": stop_new_instances,
            "retain_running": retain_running,
            "enforced": enforced,
            "hibernate": hibernate,
        },
        "version": version,
    }

    if ssm_maintenance_window:
        event["parameters"]["ssm_maintenance_window"] = ssm_maintenance_window

    handler = CliRequestHandler(event, MockLambdaContext(), MockMainLambdaEnv())
    result = handler.handle_request()
    assert is_valid_json(result)
    return result


def delete_schedule_with_cli(
    name: str,
    version: str = __version__,
) -> Any:
    event = {
        "source": "scheduler.cli",
        "action": "delete-schedule",
        "parameters": {"name": name},
        "version": version,
    }
    handler = CliRequestHandler(event, MockLambdaContext(), MockMainLambdaEnv())
    result = handler.handle_request()
    assert is_valid_json(result)
    return result


def describe_periods_with_cli(
    name: Optional[str] = None,
    version: str = __version__,
) -> Any:
    event: dict[str, Any] = {
        "source": "scheduler.cli",
        "action": "describe-periods",
        "parameters": {},
        "version": version,
    }

    if name:
        event["parameters"]["name"] = name

    handler = CliRequestHandler(event, MockLambdaContext(), MockMainLambdaEnv())
    result = handler.handle_request()
    assert is_valid_json(result)
    return result


def describe_schedules_with_cli(
    name: Optional[str] = None,
    version: str = __version__,
) -> Any:
    event: dict[str, Any] = {
        "source": "scheduler.cli",
        "action": "describe-schedules",
        "parameters": {},
        "version": version,
    }

    if name:
        event["parameters"]["name"] = name

    handler = CliRequestHandler(event, MockLambdaContext(), MockMainLambdaEnv())
    result = handler.handle_request()
    assert is_valid_json(result)
    return result


def describe_schedule_usage_with_cli(
    name: str,
    startdate: date,
    enddate: date,
    version: str = __version__,
) -> Any:
    event = {
        "source": "scheduler.cli",
        "action": "describe-schedule-usage",
        "parameters": {
            "name": name,
            "startdate": startdate.strftime("%Y%m%d"),
            "enddate": enddate.strftime("%Y%m%d"),
        },
        "version": version,
    }

    handler = CliRequestHandler(event, MockLambdaContext(), MockMainLambdaEnv())
    result = handler.handle_request()
    assert is_valid_json(result)
    return result


def get_period_from_dynamo(name: str, app_env: MainLambdaEnv) -> Any:
    table = DynamoDBUtils.get_dynamodb_table_resource_ref(app_env.config_table_name)
    result = table.get_item(Key={"type": "period", "name": name}, ConsistentRead=True)
    return result.get("Item")


def get_schedule_from_dynamo(name: str, app_env: MainLambdaEnv) -> Any:
    table = DynamoDBUtils.get_dynamodb_table_resource_ref(app_env.config_table_name)
    result = table.get_item(Key={"type": "schedule", "name": name}, ConsistentRead=True)
    return result.get("Item")
