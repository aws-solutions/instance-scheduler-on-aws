# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from datetime import datetime, time
from zoneinfo import ZoneInfo

from instance_scheduler.configuration.instance_schedule import InstanceSchedule
from instance_scheduler.configuration.running_period import RunningPeriod
from instance_scheduler.configuration.running_period_dict_element import (
    RunningPeriodDictElement,
)
from instance_scheduler.configuration.scheduling_context import SchedulingContext


def default_test_schedules() -> dict[str, InstanceSchedule]:
    schedule = default_test_schedule()
    return {schedule.name: schedule}


def default_test_schedule() -> InstanceSchedule:
    return InstanceSchedule(
        name="test-schedule",
        timezone=ZoneInfo("UTC"),
        periods=default_test_periods(),
    )


def default_test_periods() -> list[RunningPeriodDictElement]:
    return [
        {
            "period": RunningPeriod(
                name="test-period",
                begintime=time(10, 0, 0),
                endtime=time(20, 0, 0),
            )
        }
    ]


def build_scheduling_context(
    current_dt: datetime,
    schedules: dict[str, InstanceSchedule] = None,  # type: ignore[assignment]
    account_id: str = "123456789012",
    service: str = "ec2",
    region: str = "us-east-1",
    default_timezone: str = "UTC",
    scheduling_interval_minutes: int = 5,
) -> SchedulingContext:
    """abstraction layer on SchedulingContextConstructor that provides testing defaults for most values"""
    if schedules is None:
        schedules = default_test_schedules()

    return SchedulingContext(
        current_dt=current_dt,
        schedules=schedules,
        account_id=account_id,
        service=service,
        region=region,
        default_timezone=ZoneInfo(default_timezone),
        scheduling_interval_minutes=scheduling_interval_minutes,
    )
