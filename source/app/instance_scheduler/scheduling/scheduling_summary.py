# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import json
from collections import Counter
from itertools import groupby
from typing import Generic, Iterable, Iterator, TypeVar

from instance_scheduler.ops_metrics.metric_type.scheduling_action_metric import (
    ActionTaken,
    SchedulingActionMetric,
)
from instance_scheduler.scheduling.scheduling_decision import (
    ManagedInstance,
)
from instance_scheduler.scheduling.scheduling_result import SchedulingResult

T = TypeVar("T", bound=ManagedInstance)


class SchedulingSummary(Generic[T]):
    results: list[SchedulingResult[T]]

    def __init__(self, results: Iterable[SchedulingResult[T]]) -> None:
        self.results = list(results)

    def group_by_instance_type(
        self,
    ) -> Iterator[tuple[str, list[SchedulingResult[T]]]]:
        sorted_results = sorted(
            self.results, key=lambda r: r.instance.runtime_info.size
        )
        for instance_type, group in groupby(
            sorted_results, key=lambda r: r.instance.runtime_info.size
        ):
            yield instance_type, list(group)

    def group_by_schedule(
        self,
    ) -> Iterator[tuple[str, list[SchedulingResult[T]]]]:
        sorted_results = sorted(
            self.results, key=lambda r: r.instance.registry_info.schedule
        )
        for schedule, group in groupby(
            sorted_results, key=lambda r: r.instance.registry_info.schedule
        ):
            yield schedule, list(group)

    def as_actions_taken_metric(self) -> SchedulingActionMetric:
        actions = []
        for instance_type, group in self.group_by_instance_type():
            action_counts = Counter(result.action_taken for result in group)
            service = group[0].instance.registry_info.service

            for action, count in action_counts.items():
                if not action or not action.value:
                    continue

                actions.append(
                    ActionTaken(
                        instances=count,
                        action=action.value,
                        service=service,
                        instanceType=instance_type,
                    )
                )

        unique_schedules = len(
            set(result.instance.registry_info.schedule for result in self.results)
        )

        return SchedulingActionMetric(
            num_unique_schedules=unique_schedules,
            num_instances_scanned=len(self.results),
            duration_seconds=0.0,
            actions=actions,
        )

    def to_json(self) -> str:
        return json.dumps(
            [
                {
                    "instance": result.instance.registry_info.display_name,
                    "size": result.instance.runtime_info.size,
                    "schedule": result.instance.registry_info.schedule,
                    "action": (
                        result.action_taken.value if result.action_taken else None
                    ),
                    "reason": result.request_reason,
                }
                for result in self.results
            ]
        )
