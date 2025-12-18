# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from typing import Optional, Sequence

from instance_scheduler.configuration.scheduling_context import SchedulingContext
from instance_scheduler.model.period_definition import PeriodDefinition
from instance_scheduler.model.period_identifier import PeriodIdentifier
from instance_scheduler.model.schedule_definition import ScheduleDefinition


def create_simple_schedule(
    schedule_context: SchedulingContext,
    *,
    name: str = "test-schedule",
    timezone: str = "UTC",
    begintime: Optional[str] = None,
    endtime: Optional[str] = None,
    weekdays: Optional[set[str]] = None,
    monthdays: Optional[set[str]] = None,
    months: Optional[set[str]] = None,
    override_status: Optional[str] = None,
    description: Optional[str] = None,
    stop_new_instances: bool = True,
    ssm_maintenance_window: Optional[Sequence[str]] = None,
    use_maintenance_window: Optional[bool] = True,
    enforced: bool = False,
    hibernate: bool = False,
    retain_running: bool = False,
) -> tuple[ScheduleDefinition, PeriodDefinition]:
    period = PeriodDefinition(
        name=f"{name}-period",
        begintime=begintime,
        endtime=endtime,
        weekdays=weekdays,
        monthdays=monthdays,
        months=months,
    )
    schedule_context.period_store.put(period)

    schedule = ScheduleDefinition(
        name=name,
        periods=[PeriodIdentifier.of(f"{name}-period")],
        timezone=timezone,
        override_status=override_status,
        description=description,
        stop_new_instances=stop_new_instances,
        ssm_maintenance_window=ssm_maintenance_window,
        use_maintenance_window=use_maintenance_window,
        enforced=enforced,
        hibernate=hibernate,
        retain_running=retain_running,
    )
    schedule_context.schedule_store.put(schedule)

    return schedule, period


def create_multi_period_schedule(
    schedule_context: SchedulingContext,
    *,
    name: str = "test-schedule",
    timezone: str = "UTC",
    period_definitions: list[PeriodDefinition] = [],
    override_status: Optional[str] = None,
    description: Optional[str] = None,
    stop_new_instances: bool = False,
    ssm_maintenance_window: Optional[str] = None,
    enforced: bool = False,
    hibernate: bool = False,
    retain_running: bool = False,
) -> tuple[ScheduleDefinition, list[PeriodDefinition]]:
    for period_definition in period_definitions:
        schedule_context.period_store.put(period_definition)

    schedule = ScheduleDefinition(
        name=name,
        periods=[PeriodIdentifier.of(period.name) for period in period_definitions],
        timezone=timezone,
        override_status=override_status,
        description=description,
        stop_new_instances=stop_new_instances,
        ssm_maintenance_window=ssm_maintenance_window,
        enforced=enforced,
        hibernate=hibernate,
        retain_running=retain_running,
    )
    schedule_context.schedule_store.put(schedule)

    return schedule, period_definitions
