# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterator, Optional, Sequence, TypedDict

from mypy_boto3_ec2.literals import InstanceTypeType

from instance_scheduler.handler.environments.scheduling_request_environment import (
    SchedulingRequestEnvironment,
)
from instance_scheduler.handler.scheduling_request import (
    SchedulingRequest,
    SchedulingRequestHandler,
)
from instance_scheduler.model.period_definition import PeriodDefinition
from instance_scheduler.model.period_identifier import PeriodIdentifier
from instance_scheduler.model.schedule_definition import ScheduleDefinition
from instance_scheduler.model.store.in_memory_period_definition_store import (
    InMemoryPeriodDefinitionStore,
)
from instance_scheduler.model.store.in_memory_schedule_definition_store import (
    InMemoryScheduleDefinitionStore,
)
from instance_scheduler.util.scheduling_target import SchedulingTarget
from tests.context import MockLambdaContext
from tests.logger import MockLogger
from tests.test_utils.mock_scheduling_request_environment import (
    MockSchedulingRequestEnvironment,
)


def _default_schedules() -> list[ScheduleDefinition]:
    return [
        ScheduleDefinition(
            name="test-schedule",
            timezone="UTC",
            periods=[PeriodIdentifier.of(period_name="test-period")],
        )
    ]


def _default_periods() -> list[PeriodDefinition]:
    return [PeriodDefinition(name="test-period", begintime="10:00", endtime="20:00")]


def target(
    account: str = "123456789012", region: str = "us-east-1", service: str = "ec2"
) -> SchedulingTarget:
    return SchedulingTarget(account=account, region=region, service=service)


@dataclass
class SchedulingTestContext:
    schedules: list[ScheduleDefinition] = field(default_factory=_default_schedules)
    periods: list[PeriodDefinition] = field(default_factory=_default_periods)

    def run_scheduling_request_handler(
        self,
        dt: datetime,
        target: SchedulingTarget = target(),
        environment: SchedulingRequestEnvironment = MockSchedulingRequestEnvironment(),
    ) -> Any:

        schedule_store = InMemoryScheduleDefinitionStore()
        period_store = InMemoryPeriodDefinitionStore()
        for schedule in self.schedules:
            schedule_store.put(schedule)
        for period in self.periods:
            period_store.put(period)

        event: SchedulingRequest = {
            "action": "scheduler:run",
            "account": target.account,
            "region": target.region,
            "service": target.service,
            "current_dt": dt.isoformat(),
            "schedules": schedule_store.serialize(),
            "periods": period_store.serialize(),
            "dispatch_time": "2023-05-12 14:55:10.600619",
        }

        return SchedulingRequestHandler(
            event, MockLambdaContext(), environment, MockLogger()
        ).handle_request()


@contextmanager
def simple_schedule(
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
) -> Iterator[SchedulingTestContext]:
    yield SchedulingTestContext(
        schedules=[
            ScheduleDefinition(
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
        ],
        periods=[
            PeriodDefinition(
                name=f"{name}-period",
                begintime=begintime,
                endtime=endtime,
                weekdays=weekdays,
                monthdays=monthdays,
                months=months,
            )
        ],
    )


@contextmanager
def multi_period_schedule(
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
) -> Iterator[SchedulingTestContext]:
    yield SchedulingTestContext(
        schedules=[
            ScheduleDefinition(
                name=name,
                periods=[
                    PeriodIdentifier.of(period.name) for period in period_definitions
                ],
                timezone=timezone,
                override_status=override_status,
                description=description,
                stop_new_instances=stop_new_instances,
                ssm_maintenance_window=ssm_maintenance_window,
                enforced=enforced,
                hibernate=hibernate,
                retain_running=retain_running,
            )
        ],
        periods=period_definitions,
    )


class PeriodWithDesiredType(TypedDict):
    period: PeriodDefinition
    desired_type: Optional[InstanceTypeType]


@contextmanager
def resizable_multi_period_schedule(
    name: str = "test-schedule",
    timezone: str = "UTC",
    period_definitions: list[PeriodWithDesiredType] = [],
    override_status: Optional[str] = None,
    description: Optional[str] = None,
    stop_new_instances: bool = False,
    ssm_maintenance_window: Optional[str] = None,
    enforced: bool = False,
    hibernate: bool = False,
    retain_running: bool = False,
) -> Iterator[SchedulingTestContext]:
    yield SchedulingTestContext(
        schedules=[
            ScheduleDefinition(
                name=name,
                periods=[
                    PeriodIdentifier.of(period["period"].name, period["desired_type"])
                    for period in period_definitions
                ],
                timezone=timezone,
                override_status=override_status,
                description=description,
                stop_new_instances=stop_new_instances,
                ssm_maintenance_window=ssm_maintenance_window,
                enforced=enforced,
                hibernate=hibernate,
                retain_running=retain_running,
            )
        ],
        periods=[period_with_type["period"] for period_with_type in period_definitions],
    )
