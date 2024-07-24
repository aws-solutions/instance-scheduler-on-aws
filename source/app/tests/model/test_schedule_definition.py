# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from datetime import time

import pytest
from mypy_boto3_dynamodb.type_defs import AttributeValueTypeDef

from instance_scheduler.configuration.instance_schedule import InstanceSchedule
from instance_scheduler.configuration.running_period import RunningPeriod
from instance_scheduler.configuration.running_period_dict_element import (
    RunningPeriodDictElement,
)
from instance_scheduler.model.period_definition import PeriodDefinition
from instance_scheduler.model.period_identifier import PeriodIdentifier
from instance_scheduler.model.schedule_definition import (
    InvalidScheduleDefinition,
    ScheduleDefinition,
)
from instance_scheduler.model.store.period_definition_store import PeriodDefinitionStore
from tests.test_utils.testsuite_env import TestSuiteEnv


def test_default_schedule_flags_match_expected(
    period_store: PeriodDefinitionStore,
) -> None:
    schedule_def = ScheduleDefinition(name="test-schedule", override_status="running")

    schedule = schedule_def.to_instance_schedule(period_store)

    assert schedule.stop_new_instances is True
    assert schedule.enforced is False
    assert schedule.retain_running is False
    assert schedule.hibernate is False


def test_schedule_definition_defaults_match_instance_schedule_defaults(
    period_store: PeriodDefinitionStore, test_suite_env: TestSuiteEnv
) -> None:
    """
    InstanceSchedule and ScheduleDefinition each define their defaults separately, but these need to match
    to avoid unexpected behavior
    """

    schedule_def = ScheduleDefinition(name="test-schedule", override_status="running")

    schedule_from_def = schedule_def.to_instance_schedule(period_store)

    manual_built_schedule = InstanceSchedule(
        name="test-schedule",
        override_status="running",
        timezone=test_suite_env.default_timezone,
    )

    assert schedule_from_def == manual_built_schedule


@pytest.mark.parametrize("tz_str", ["", None])
def test_timezone_uses_default_timezone_when_not_provided(
    tz_str: str, test_suite_env: TestSuiteEnv, period_store: PeriodDefinitionStore
) -> None:
    schedule_def = ScheduleDefinition(
        name="test-schedule", timezone=tz_str, override_status="running"
    )

    schedule = schedule_def.to_instance_schedule(period_store)

    assert schedule.timezone == test_suite_env.default_timezone


def test_to_schedule_when_period_exists(
    config_table: str,
    test_suite_env: TestSuiteEnv,
    period_store: PeriodDefinitionStore,
) -> None:
    period_store.put(PeriodDefinition(name="period", begintime="05:00"))
    schedule_def = ScheduleDefinition(
        name="test-schedule", periods=[PeriodIdentifier("period")]
    )

    schedule = schedule_def.to_instance_schedule(period_store)

    assert schedule == InstanceSchedule(
        name="test-schedule",
        timezone=test_suite_env.default_timezone,
        periods=[
            RunningPeriodDictElement(
                period=RunningPeriod(name="period", begintime=time(5, 0, 0))
            )
        ],
    )


def test_to_item_from_item_round_trip_with_minimal_flags() -> None:
    schedule = ScheduleDefinition(name="test-schedule", override_status="running")
    item = schedule.to_item()
    schedule2 = ScheduleDefinition.from_item(item)
    assert schedule == schedule2


def test_to_item_from_item_round_trip_with_all_flags() -> None:
    schedule = ScheduleDefinition(
        name="test-schedule",
        timezone="America/New_York",
        periods=[PeriodIdentifier("period")],
        override_status="stopped",
        description="test-description",
        stop_new_instances=True,
        enforced=True,
        hibernate=True,
        retain_running=True,
        configured_in_stack="some_stack_arn",
        ssm_maintenance_window=["some_ssm_window_name"],
    )
    item = schedule.to_item()
    schedule2 = ScheduleDefinition.from_item(item)
    assert schedule == schedule2


def test_from_item_with_string_ssm_maint_win() -> None:
    maintenance_window_name = "some_ssm_window_name"
    item: dict[str, AttributeValueTypeDef] = {
        "type": {"S": "schedule"},
        "name": {"S": "test-schedule"},
        "periods": {"SS": ["period"]},
        "ssm_maintenance_window": {
            "S": maintenance_window_name
        },  # tests backwards compatibility with str values
    }
    schedule2 = ScheduleDefinition.from_item(item)
    assert schedule2.ssm_maintenance_window == [maintenance_window_name]


def test_to_item_strips_empty_values() -> None:
    item = ScheduleDefinition(
        name="test-schedule",
        periods=[PeriodIdentifier("period")],
    ).to_item()

    assert item == {
        "type": {"S": "schedule"},
        "name": {"S": "test-schedule"},
        "periods": {"SS": ["period"]},
    }


def test_to_item_includes_all_values_when_provided() -> None:
    item = ScheduleDefinition(
        name="test-schedule",
        timezone="America/New_York",
        periods=[PeriodIdentifier("period")],
        override_status="stopped",
        description="test-description",
        stop_new_instances=True,
        enforced=True,
        hibernate=True,
        retain_running=True,
        configured_in_stack="some_stack_arn",
        ssm_maintenance_window=["some_ssm_window_name"],
    ).to_item()

    assert item == {
        "type": {"S": "schedule"},
        "name": {"S": "test-schedule"},
        "periods": {"SS": ["period"]},
        "timezone": {"S": "America/New_York"},
        "override_status": {"S": "stopped"},
        "description": {"S": "test-description"},
        "stop_new_instances": {"BOOL": True},
        "enforced": {"BOOL": True},
        "hibernate": {"BOOL": True},
        "retain_running": {"BOOL": True},
        "configured_in_stack": {"S": "some_stack_arn"},
        "ssm_maintenance_window": {"SS": ["some_ssm_window_name"]},
    }


# region Validation Tests
def test_accepts_basic_schedule() -> None:
    ScheduleDefinition(
        name="test-schedule",
        timezone="America/New_York",
        periods=[PeriodIdentifier("period")],
    )


def test_accepts_schedule_with_all_flags() -> None:
    ScheduleDefinition(
        name="test-schedule",
        timezone="America/New_York",
        periods=[PeriodIdentifier("period")],
        override_status="stopped",
        description="test-description",
        stop_new_instances=True,
        enforced=True,
        hibernate=True,
        retain_running=True,
        configured_in_stack="some_stack_arn",
        ssm_maintenance_window=["some_ssm_window_name"],
    )


@pytest.mark.parametrize("invalid", ["fake-timezone"])
def test_rejects_invalid_timezone(invalid: str) -> None:
    with pytest.raises(InvalidScheduleDefinition):
        ScheduleDefinition(
            name="test-schedule",
            timezone=invalid,
            periods=[PeriodIdentifier("period")],
        )


@pytest.mark.parametrize(
    "tz_str", ["America/New_York", "America/Los_Angeles", "Asia/Tokyo"]
)
def test_accepts_valid_timezones(tz_str: str) -> None:
    schedule = ScheduleDefinition(
        name="test-schedule",
        timezone=tz_str,
        periods=[PeriodIdentifier("period")],
    )

    assert str(schedule.timezone) == tz_str


def test_rejects_when_no_periods_or_overrides_provided() -> None:
    with pytest.raises(InvalidScheduleDefinition):
        ScheduleDefinition(
            name="test-schedule",
            timezone="America/New_York",
        )


def test_accepts_override_status_with_no_periods() -> None:
    ScheduleDefinition(
        name="test-schedule",
        timezone="America/New_York",
        override_status="running",
    )


@pytest.mark.parametrize("status", ["invalid"])
def test_rejects_invalid_override_status(status: str) -> None:
    with pytest.raises(InvalidScheduleDefinition):
        ScheduleDefinition(
            name="test-schedule",
            timezone="America/New_York",
            periods=[PeriodIdentifier("period")],
            override_status=status,
        )


@pytest.mark.parametrize("status", ["running", "stopped", "RUNNING", "StoPped"])
def test_accepts_valid_override_status(status: str) -> None:
    ScheduleDefinition(
        name="test-schedule",
        timezone="America/New_York",
        periods=[PeriodIdentifier("period")],
        override_status=status,
    )


# endregion
