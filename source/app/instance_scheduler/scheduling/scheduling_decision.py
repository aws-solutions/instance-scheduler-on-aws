# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Generic, Iterable, Optional, TypeVar, assert_never

from instance_scheduler.configuration.instance_schedule import InstanceSchedule
from instance_scheduler.model.managed_instance import (
    RegisteredInstance,
)
from instance_scheduler.scheduling.states import InstanceState, ScheduleState
from instance_scheduler.util.arn import ARN


class RuntimeInfo(ABC):
    tags: dict[str, str]
    arn: ARN

    @property
    @abstractmethod
    def is_in_schedulable_state(self) -> bool:
        pass

    @property
    @abstractmethod
    def is_running(self) -> bool:
        pass

    @property
    @abstractmethod
    def is_stopped(self) -> bool:
        pass

    @property
    @abstractmethod
    def size(self) -> str:
        pass


@dataclass
class ManagedInstance:
    registry_info: RegisteredInstance
    runtime_info: RuntimeInfo

    @property
    def arn(self) -> ARN:
        return self.registry_info.arn

    @property
    def tags(self) -> dict[str, str]:
        return self.runtime_info.tags


class RequestedAction(Enum):
    DO_NOTHING = "None"
    START = "Start"
    STOP = "Stop"
    CONFIGURE = "Configure"


T = TypeVar("T", bound=ManagedInstance)


@dataclass()
class SchedulingDecision(Generic[T]):
    instance: T
    action: RequestedAction
    new_stored_state: InstanceState
    reason: str

    @property
    def stored_state(self) -> InstanceState:
        """Current stored state from the instance registry"""
        return self.instance.registry_info.stored_state


def make_scheduling_decision(  # NOSONAR -- cognitive complexity
    instance: T,
    schedule: InstanceSchedule,
    current_dt: datetime,
    maintenance_windows: Optional[Iterable[InstanceSchedule]] = None,
) -> SchedulingDecision[T]:
    """Standalone version of the scheduling decision logic."""
    stored_state = instance.registry_info.stored_state

    if schedule.use_maintenance_window:
        if maintenance_windows is None:
            maintenance_windows = []
        for mw in maintenance_windows:
            if mw.get_desired_state(current_dt)[0] == ScheduleState.RUNNING:
                return SchedulingDecision(
                    instance=instance,
                    action=RequestedAction.START,
                    new_stored_state=InstanceState.RUNNING,
                    reason=f"In active maintenance window {mw.name}",
                )

    schedule_state, _, _ = schedule.get_desired_state(current_dt)

    match schedule_state:
        case ScheduleState.STOPPED:
            if (
                stored_state == InstanceState.UNKNOWN
                and not schedule.stop_new_instances
            ):
                return SchedulingDecision(
                    instance=instance,
                    action=RequestedAction.DO_NOTHING,
                    new_stored_state=InstanceState.STOPPED,
                    reason="stop_new_instances is disabled",
                )

            if schedule.enforced:
                return SchedulingDecision(
                    instance=instance,
                    action=RequestedAction.STOP,
                    new_stored_state=InstanceState.STOPPED,
                    reason="enforced is enabled",
                )

            if stored_state == InstanceState.RETAIN_RUNNING and schedule.retain_running:
                return SchedulingDecision(
                    instance=instance,
                    action=RequestedAction.DO_NOTHING,
                    new_stored_state=InstanceState.STOPPED,
                    reason="Instance is in the RETAIN_RUNNING state",
                )

            if stored_state != schedule_state:  # type: ignore[comparison-overlap]
                return SchedulingDecision(
                    instance=instance,
                    action=RequestedAction.STOP,
                    new_stored_state=InstanceState.STOPPED,
                    reason=f"State transition from {stored_state} to {schedule_state}",
                )
            else:
                return SchedulingDecision(
                    instance=instance,
                    action=RequestedAction.DO_NOTHING,
                    new_stored_state=InstanceState.STOPPED,
                    reason=f"No schedule state transition detected (prev state: {stored_state}, new state: {schedule_state})",
                )

        case ScheduleState.RUNNING:
            if schedule.enforced:
                return SchedulingDecision(
                    instance=instance,
                    action=RequestedAction.START,
                    new_stored_state=InstanceState.RUNNING,
                    reason="enforced is enabled",
                )

            if schedule.retain_running and stored_state == InstanceState.STOPPED:
                return SchedulingDecision(
                    instance=instance,
                    action=RequestedAction.DO_NOTHING,
                    new_stored_state=InstanceState.RETAIN_RUNNING,
                    reason="Instance appears to have already been started -- apply retain_running flag",
                )

            if stored_state == InstanceState.RETAIN_RUNNING:
                return SchedulingDecision(
                    instance=instance,
                    action=RequestedAction.DO_NOTHING,
                    new_stored_state=InstanceState.RETAIN_RUNNING,
                    reason="Instance in retain_running state -- do not remove the flag",
                )

            if stored_state == InstanceState.START_FAILED:
                return SchedulingDecision(
                    instance=instance,
                    action=RequestedAction.START,
                    new_stored_state=InstanceState.RUNNING,
                    reason="Instance failed to start previously. Attempting to retry",
                )

            if stored_state != schedule_state:  # type: ignore[comparison-overlap]
                return SchedulingDecision(
                    instance=instance,
                    action=RequestedAction.START,
                    new_stored_state=InstanceState.RUNNING,
                    reason=f"State transition from {stored_state} to {schedule_state}",
                )
            else:
                return SchedulingDecision(
                    instance=instance,
                    action=RequestedAction.DO_NOTHING,
                    new_stored_state=InstanceState.RUNNING,
                    reason=f"No schedule state transition detected (prev state: {stored_state}, new state: {schedule_state})",
                )

        case ScheduleState.ANY:
            return SchedulingDecision(
                instance=instance,
                action=RequestedAction.DO_NOTHING,
                new_stored_state=InstanceState.ANY,
                reason="Schedule is in the any state",
            )

        case _ as unreachable:
            assert_never(unreachable)
