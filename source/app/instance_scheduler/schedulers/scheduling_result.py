# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from typing import Any, TypedDict

from instance_scheduler.ops_metrics.metric_type.scheduling_action_metric import (
    ActionTaken,
)
from instance_scheduler.ops_monitoring.instance_counts import InstanceCountsAggregator
from instance_scheduler.schedulers.scheduling_decision import (
    SchedulingAction,
    SchedulingDecision,
)
from instance_scheduler.service.abstract_instance import AbstractInstance


class ScheduleItem(TypedDict):
    schedule: str


# dict[instance_id, schedule]
InstanceItem = dict[str, ScheduleItem]


class SchedulingResult:
    """A result object for accumulating the final output of a scheduling execution"""

    def __init__(self) -> None:
        self.instance_counts = InstanceCountsAggregator()

        # format of started/stopped/resized fields:
        # {
        #     instance_type: [
        #         {instance_id: {"schedule": schedule_name}}
        #         {instance_id: {"schedule": schedule_name}}
        #     ]
        # }
        self.started: dict[str, list[InstanceItem]] = {}
        self.stopped: dict[str, list[InstanceItem]] = {}
        self.resized: dict[str, list[InstanceItem]] = {}

    def to_output_dict(self) -> dict[str, Any]:
        return {
            "num_schedules_checked": len(self.instance_counts.by_schedule()),
            "instance_counts": self.instance_counts.by_type(),
            "started": self.started,
            "stopped": self.stopped,
            "resized": self.resized,
        }

    def to_actions_taken(self, service: str) -> list[ActionTaken]:
        actions_taken = []
        for instance_type, actions in self.started.items():
            actions_taken.append(
                ActionTaken(
                    instanceType=instance_type,
                    instances=len(actions),
                    action="Started",
                    service=service,
                )
            )
        for instance_type, actions in self.stopped.items():
            actions_taken.append(
                ActionTaken(
                    instanceType=instance_type,
                    instances=len(actions),
                    action="Stopped",
                    service=service,
                )
            )
        for instance_type, actions in self.resized.items():
            # instance_type str is of format from-to
            actions_taken.append(
                ActionTaken(
                    instanceType=instance_type,
                    instances=len(actions),
                    action="Resized",
                    service=service,
                )
            )

        return actions_taken

    def add_checked_instance(self, instance: AbstractInstance) -> None:
        self.instance_counts.by_type().increment(
            instance.instance_type, instance.current_state
        )
        self.instance_counts.by_schedule().increment(
            instance.schedule_name, instance.current_state
        )

    def add_resize_action(self, instance: AbstractInstance, resized_to: str) -> None:
        type_str = f"{instance.instance_type}-{resized_to}"
        if type_str not in self.resized:
            self.resized[type_str] = []

        self.resized[type_str].append(
            {instance.id: {"schedule": instance.schedule_name}}
        )

    def add_completed_action(self, action: SchedulingDecision) -> None:
        instance_type = action.instance.instance_type

        if action.action == SchedulingAction.START:
            if instance_type not in self.started:
                self.started[instance_type] = []

            self.started[instance_type].append(
                {action.instance.id: {"schedule": action.instance.schedule_name}}
            )

        elif action.action == SchedulingAction.STOP:
            if instance_type not in self.stopped:
                self.stopped[instance_type] = []

            self.stopped[instance_type].append(
                {action.instance.id: {"schedule": action.instance.schedule_name}}
            )
