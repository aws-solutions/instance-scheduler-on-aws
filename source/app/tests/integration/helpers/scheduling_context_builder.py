# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from datetime import datetime, time
from typing import Optional
from zoneinfo import ZoneInfo

from instance_scheduler.configuration.instance_schedule import InstanceSchedule
from instance_scheduler.configuration.running_period import RunningPeriod
from instance_scheduler.configuration.running_period_dict_element import (
    RunningPeriodDictElement,
)
from instance_scheduler.configuration.scheduling_context import (
    SchedulingContext,
    TagTemplate,
)
from instance_scheduler.handler.scheduling_request import SchedulerRequest


def default_test_schedules() -> dict[str, InstanceSchedule]:
    schedule = default_test_schedule()
    return {schedule.name: schedule}


def default_test_schedule() -> InstanceSchedule:
    return InstanceSchedule(
        name="test-schedule",
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


def custom_schedule(
    periods: list[RunningPeriodDictElement] = default_test_periods(),
    # mutable warning is desired behavior here as an empty period list should NOT be resolved to the default
    timezone: str = "UTC",
    override_status: Optional[str] = None,
    description: Optional[str] = None,
    use_metrics: Optional[bool] = None,
    stop_new_instances: Optional[bool] = None,
    use_maintenance_window: Optional[bool] = False,
    ssm_maintenance_window: Optional[str] = None,
    enforced: Optional[bool] = False,
    hibernate: Optional[bool] = False,
    retain_running: Optional[bool] = False,
) -> dict[str, InstanceSchedule]:
    return {
        "test-schedule": InstanceSchedule(
            name="test-schedule",
            periods=periods,
            timezone=timezone,
            override_status=override_status,
            description=description,
            use_metrics=use_metrics,
            stop_new_instances=stop_new_instances,
            use_maintenance_window=use_maintenance_window,
            ssm_maintenance_window=ssm_maintenance_window,
            enforced=enforced,
            hibernate=hibernate,
            retain_running=retain_running,
        )
    }


def build_context(
    current_dt: datetime,
    schedules: dict[str, InstanceSchedule] = None,  # type: ignore[assignment]
    account_id: str = "",
    service: str = "ec2",
    region: str = "us-east-1",
    tag_name: str = "Schedule",
    default_timezone: str = "UTC",
    schedule_clusters: bool = False,
    trace: bool = False,
    enable_ssm_maintenance_windows: bool = False,
    use_metrics: bool = False,
    namespace: str = "namespace",
    aws_partition: str = "aws",
    scheduler_role_name: str = "scheduler_role",
    organization_id: str = "",
    schedule_lambda_account: bool = True,
    create_rds_snapshot: bool = False,
    started_tags: Optional[list[TagTemplate]] = None,
    stopped_tags: Optional[list[TagTemplate]] = None,
) -> SchedulingContext:
    """abstraction layer on SchedulingContextConstructor that provides testing defaults for most values"""
    if schedules is None:
        schedules = default_test_schedules()
    if started_tags is None:
        started_tags = []
    if stopped_tags is None:
        stopped_tags = []

    return SchedulingContext(
        current_dt=current_dt,
        schedules=schedules,
        account_id=account_id,
        service=service,
        region=region,
        tag_name=tag_name,
        default_timezone=ZoneInfo(default_timezone),
        schedule_clusters=schedule_clusters,
        trace=trace,
        enable_ssm_maintenance_windows=enable_ssm_maintenance_windows,
        use_metrics=use_metrics,
        namespace=namespace,
        aws_partition=aws_partition,
        scheduler_role_name=scheduler_role_name,
        organization_id=organization_id,
        schedule_lambda_account=schedule_lambda_account,
        create_rds_snapshot=create_rds_snapshot,
        started_tags=started_tags,
        stopped_tags=stopped_tags,
    )


def build_scheduling_event(scheduling_context: SchedulingContext) -> SchedulerRequest:
    return {
        "action": "scheduler:run",
        "configuration": scheduling_context.to_dict(),
        "dispatch_time": "2023-05-12 14:55:10.600619",
    }
