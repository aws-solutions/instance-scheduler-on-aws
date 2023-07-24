# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from datetime import date
from typing import Any, Optional, Sequence

from instance_scheduler.handler.cli import CliHandler
from instance_scheduler.util.app_env import AppEnv
from instance_scheduler.util.dynamodb_utils import DynamoDBUtils
from tests.context import MockLambdaContext
from tests.test_utils.unordered_list import UnorderedList


def test_is_handling_request() -> None:
    assert CliHandler.is_handling_request(
        {"source": "scheduler.cli", "action": "something"}
    )

    assert not CliHandler.is_handling_request(
        {"source": "anything.else", "action": "another_thing"}
    )


def test_create_schedule_throws_error_when_period_not_found(config_table: None) -> None:
    result = create_schedule_with_cli(periods=["office-hours"])
    assert result == {"Error": "error: not found: period office-hours does not exist"}


def test_create_schedule_with_2_periods(config_table: None, app_env: AppEnv) -> None:
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
            "UseMaintenanceWindow": False,
            "RetainRunning": False,
            "Enforced": False,
            "Hibernate": False,
            "UseMetrics": False,
            "Type": "schedule",
        }
    }

    created_schedule = get_schedule_from_dynamo("cli-schedule", app_env)
    assert created_schedule == {
        "type": "schedule",
        "name": "cli-schedule",
        "periods": {"period1", "period2"},
        "stop_new_instances": True,
        "use_maintenance_window": False,
        "retain_running": False,
        "enforced": False,
        "hibernate": False,
        "use_metrics": False,
    }


def test_create_schedule_throws_error_when_schedule_already_exists(
    config_table: None,
) -> None:
    create_period_with_cli(name="period1")
    create_schedule_with_cli(name="cli-schedule", periods=["period1"])
    result = create_schedule_with_cli(name="cli-schedule", periods=["period1"])

    assert result == {"Error": "error: schedule cli-schedule already exists"}


def test_delete_existing_schedule(config_table: None, app_env: AppEnv) -> None:
    create_period_with_cli(name="period1")
    create_period_with_cli(name="period2")
    create_schedule_with_cli(periods=["period1", "period2"], name="cli-schedule")

    assert get_schedule_from_dynamo("cli-schedule", app_env) is not None
    result = delete_schedule_with_cli("cli-schedule")
    assert result == {"Schedule": "cli-schedule"}
    assert get_schedule_from_dynamo("cli-schedule", app_env) is None


def test_delete_nonexisting_schedule_returns_error(config_table: None) -> None:
    result = delete_period_with_cli("cli-schedule")
    assert result == {"Error": "not found: period cli-schedule does not exist"}


def test_create_basic_period(config_table: None, app_env: AppEnv) -> None:
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

    created_period = get_period_from_dynamo(name="cli-period", app_env=app_env)
    assert created_period == {
        "type": "period",
        "name": "cli-period",
        "begintime": "10:00",
        "endtime": "20:00",
    }


def test_create_period_throws_error_when_period_already_exists(
    config_table: None,
) -> None:
    create_period_with_cli(name="cli-period")
    result = create_period_with_cli(name="cli-period")

    assert result == {"Error": "error: period cli-period already exists"}


def test_delete_existing_period(config_table: None, app_env: AppEnv) -> None:
    create_period_with_cli(name="cli-period")

    assert get_period_from_dynamo("cli-period", app_env) is not None
    result = delete_period_with_cli("cli-period")
    assert result == {"Period": "cli-period"}
    assert get_period_from_dynamo("cli-period", app_env) is None


def test_delete_nonexisting_period_returns_error(config_table: None) -> None:
    result = delete_period_with_cli("cli-period")
    assert result == {"Error": "not found: period cli-period does not exist"}


def test_describe_all_periods_is_empty_when_no_periods_created(
    config_table: None,
) -> None:
    result = describe_periods()
    assert result == {"Periods": []}


def test_describe_all_periods_returns_created_periods(config_table: None) -> None:
    create_period_with_cli("period1", begintime="5:00", endtime="10:00"),
    create_period_with_cli("period2", begintime="12:00", endtime="14:00")
    result = describe_periods()
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


def test_describe_specific_period_returns_expected_period(config_table: None) -> None:
    create_period_with_cli("period1", begintime="5:00", endtime="10:00"),
    create_period_with_cli("period2", begintime="12:00", endtime="14:00")
    result = describe_periods("period1")
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
    create_period_with_cli("period1", begintime="5:00", endtime="10:00"),
    create_period_with_cli("period2", begintime="12:00", endtime="14:00")
    result = describe_periods("period3")
    assert result == {"Error": "not found: period period3 does not exist"}


def test_describe_all_schedules_is_empty_when_no_schedules_created(
    config_table: None,
) -> None:
    result = describe_schedules()
    assert result == {"Schedules": []}


def test_describe_all_schedules_returns_created_schedules(config_table: None) -> None:
    create_period_with_cli("period1", begintime="5:00", endtime="10:00"),
    create_period_with_cli("period2", begintime="12:00", endtime="14:00")
    create_schedule_with_cli(
        periods=["period1"], name="schedule1", stop_new_instances=False
    )
    create_schedule_with_cli(periods=["period2"], name="schedule2", retain_running=True)

    result = describe_schedules()
    assert result == {
        "Schedules": UnorderedList(
            [
                {
                    "Type": "schedule",
                    "Name": "schedule1",
                    "Periods": ["period1"],
                    "StopNewInstances": False,
                    "UseMaintenanceWindow": False,
                    "RetainRunning": False,
                    "Enforced": False,
                    "Hibernate": False,
                    "UseMetrics": False,
                },
                {
                    "Type": "schedule",
                    "Name": "schedule2",
                    "Periods": ["period2"],
                    "StopNewInstances": True,
                    "UseMaintenanceWindow": False,
                    "RetainRunning": True,
                    "Enforced": False,
                    "Hibernate": False,
                    "UseMetrics": False,
                },
            ]
        )
    }


def test_describe_specific_schedule_returns_expected_schedule(
    config_table: None,
) -> None:
    create_period_with_cli("period1", begintime="5:00", endtime="10:00"),
    create_period_with_cli("period2", begintime="12:00", endtime="14:00")
    create_schedule_with_cli(
        periods=["period1"],
        name="schedule1",
        use_maintenance_window=True,
        ssm_maintenance_window="window",
    )
    create_schedule_with_cli(periods=["period2"], name="schedule2", enforced=True)

    result = describe_schedules("schedule1")
    assert result == {
        "Schedules": [
            {
                "Type": "schedule",
                "Name": "schedule1",
                "Periods": ["period1"],
                "StopNewInstances": True,
                "UseMaintenanceWindow": True,
                "SsmMaintenanceWindow": "window",
                "RetainRunning": False,
                "Enforced": False,
                "Hibernate": False,
                "UseMetrics": False,
            },
        ]
    }


def test_describe_specific_schedule_returns_error_when_not_exists(
    config_table: None,
) -> None:
    create_period_with_cli("period1", begintime="5:00", endtime="10:00"),
    create_period_with_cli("period2", begintime="12:00", endtime="14:00")
    create_schedule_with_cli(
        periods=["period1"],
        name="schedule1",
        use_maintenance_window=True,
        ssm_maintenance_window="window",
    )
    create_schedule_with_cli(periods=["period2"], name="schedule2", enforced=True)

    result = describe_schedules("schedule3")
    assert result == {"Error": "not found: schedule schedule3 does not exist"}


def test_describe_schedule_usage(config_table: None) -> None:
    create_period_with_cli("cli-period", begintime="9:00", endtime="17:00"),
    create_schedule_with_cli(periods=["cli-period"], name="cli-schedule")
    result = describe_schedule_usage(
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


def test_update_period(config_table: None, app_env: AppEnv) -> None:
    create_period_with_cli("cli-period", begintime="2:00", endtime="4:00")
    result = update_period_with_cli("cli-period", begintime="12:00", endtime="15:00")

    assert result == {
        "Period": {
            "Begintime": "12:00",
            "Endtime": "15:00",
            "Name": "cli-period",
            "Type": "period",
        }
    }

    updated_period = get_period_from_dynamo("cli-period", app_env)
    assert updated_period == {
        "type": "period",
        "name": "cli-period",
        "begintime": "12:00",
        "endtime": "15:00",
    }


def test_update_period_returns_error_when_period_does_not_exist(
    config_table: None,
) -> None:
    result = update_period_with_cli("cli-period", begintime="12:00", endtime="15:00")

    assert result == {"Error": "not found: period cli-period does not exist"}


def test_update_schedule(config_table: None, app_env: AppEnv) -> None:
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
            "UseMaintenanceWindow": False,
            "RetainRunning": False,
            "Enforced": True,
            "Hibernate": False,
            "UseMetrics": False,
            "Type": "schedule",
        }
    }

    updated_schedule = get_schedule_from_dynamo("cli-schedule", app_env)
    assert updated_schedule == {
        "type": "schedule",
        "name": "cli-schedule",
        "periods": {"period1", "period2"},
        "stop_new_instances": True,
        "use_maintenance_window": False,
        "retain_running": False,
        "enforced": True,
        "hibernate": False,
        "use_metrics": False,
    }


def test_update_schedule_returns_error_when_schedule_does_not_exist(
    config_table: None,
) -> None:
    create_period_with_cli("period1")
    result = update_schedule_with_cli(name="cli-schedule", periods=["period1"])

    assert result == {"Error": "not found: schedule cli-schedule does not exist"}


def test_update_schedule_returns_error_when_period_does_not_exist(
    config_table: None,
) -> None:
    result = update_schedule_with_cli(name="cli-schedule", periods=["period1"])

    assert result == {"Error": "error: not found: period period1 does not exist"}


# ------------------------------Begin Helpers------------------------------ #


def create_period_with_cli(
    name: str = "cli-period", begintime: str = "10:00", endtime: str = "20:00"
) -> Any:
    event = {
        "source": "scheduler.cli",
        "action": "create-period",
        "parameters": {"name": name, "begintime": begintime, "endtime": endtime},
    }

    handler = CliHandler(event, MockLambdaContext())
    return handler.handle_request()


def update_period_with_cli(
    name: str = "cli-period", begintime: str = "10:00", endtime: str = "20:00"
) -> Any:
    event = {
        "source": "scheduler.cli",
        "action": "update-period",
        "parameters": {"name": name, "begintime": begintime, "endtime": endtime},
    }

    handler = CliHandler(event, MockLambdaContext())
    return handler.handle_request()


def delete_period_with_cli(name: str) -> Any:
    event = {
        "source": "scheduler.cli",
        "action": "delete-period",
        "parameters": {"name": name},
    }
    handler = CliHandler(event, MockLambdaContext())
    return handler.handle_request()


def create_schedule_with_cli(
    periods: Sequence[str],
    name: str = "cli-schedule",
    stop_new_instances: bool = True,
    use_maintenance_window: bool = False,
    retain_running: bool = False,
    enforced: bool = False,
    hibernate: bool = False,
    use_metrics: bool = False,
    ssm_maintenance_window: Optional[str] = None,
) -> Any:
    event: dict[str, Any] = {
        "source": "scheduler.cli",
        "action": "create-schedule",
        "parameters": {
            "name": name,
            "periods": ",".join(periods),
            "stop_new_instances": stop_new_instances,
            "use_maintenance_window": use_maintenance_window,
            "retain_running": retain_running,
            "enforced": enforced,
            "hibernate": hibernate,
            "use-metrics": use_metrics,
        },
    }

    if ssm_maintenance_window:
        event["parameters"]["ssm_maintenance_window"] = ssm_maintenance_window

    handler = CliHandler(event, MockLambdaContext())
    return handler.handle_request()


def update_schedule_with_cli(
    periods: Sequence[str],
    name: str = "cli-schedule",
    stop_new_instances: bool = True,
    use_maintenance_window: bool = False,
    retain_running: bool = False,
    enforced: bool = False,
    hibernate: bool = False,
    use_metrics: bool = False,
    ssm_maintenance_window: Optional[str] = None,
) -> Any:
    event: dict[str, Any] = {
        "source": "scheduler.cli",
        "action": "update-schedule",
        "parameters": {
            "name": name,
            "periods": ",".join(periods),
            "stop_new_instances": stop_new_instances,
            "use_maintenance_window": use_maintenance_window,
            "retain_running": retain_running,
            "enforced": enforced,
            "hibernate": hibernate,
            "use-metrics": use_metrics,
        },
    }

    if ssm_maintenance_window:
        event["parameters"]["ssm_maintenance_window"] = ssm_maintenance_window

    handler = CliHandler(event, MockLambdaContext())
    return handler.handle_request()


def delete_schedule_with_cli(name: str) -> Any:
    event = {
        "source": "scheduler.cli",
        "action": "delete-schedule",
        "parameters": {"name": name},
    }
    handler = CliHandler(event, MockLambdaContext())
    return handler.handle_request()


def describe_periods(name: Optional[str] = None) -> Any:
    event: dict[str, Any] = {
        "source": "scheduler.cli",
        "action": "describe-periods",
        "parameters": {},
    }

    if name:
        event["parameters"]["name"] = name

    handler = CliHandler(event, MockLambdaContext())
    return handler.handle_request()


def describe_schedules(name: Optional[str] = None) -> Any:
    event: dict[str, Any] = {
        "source": "scheduler.cli",
        "action": "describe-schedules",
        "parameters": {},
    }

    if name:
        event["parameters"]["name"] = name

    handler = CliHandler(event, MockLambdaContext())
    return handler.handle_request()


def describe_schedule_usage(name: str, startdate: date, enddate: date) -> Any:
    event = {
        "source": "scheduler.cli",
        "action": "describe-schedule-usage",
        "parameters": {
            "name": name,
            "startdate": startdate.strftime("%Y%m%d"),
            "enddate": enddate.strftime("%Y%m%d"),
        },
    }

    handler = CliHandler(event, MockLambdaContext())
    return handler.handle_request()


def get_period_from_dynamo(name: str, app_env: AppEnv) -> Any:
    table = DynamoDBUtils.get_dynamodb_table_resource_ref(app_env.config_table_name)
    result = table.get_item(Key={"type": "period", "name": name}, ConsistentRead=True)
    return result.get("Item")


def get_schedule_from_dynamo(name: str, app_env: AppEnv) -> Any:
    table = DynamoDBUtils.get_dynamodb_table_resource_ref(app_env.config_table_name)
    result = table.get_item(Key={"type": "schedule", "name": name}, ConsistentRead=True)
    return result.get("Item")
