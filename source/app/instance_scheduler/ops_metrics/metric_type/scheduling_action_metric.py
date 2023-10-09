# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from dataclasses import dataclass
from typing import ClassVar

from instance_scheduler.ops_metrics import GatheringFrequency
from instance_scheduler.ops_metrics.metric_type.ops_metric import OpsMetric


@dataclass(frozen=True)
class ActionTaken:
    instances: int
    action: str  # Literal["started", "stopped", "resized"]
    service: str  # Literal["ec2", "rds"]
    instanceType: str


@dataclass(frozen=True)
class SchedulingActionMetric(OpsMetric):
    num_unique_schedules: int  # num schedules configured in that region, not the number that took action
    num_instances_scanned: int
    duration_seconds: float
    actions: list[ActionTaken]
    event_name: ClassVar[str] = "scheduling_action"
    collection_frequency: ClassVar[GatheringFrequency] = GatheringFrequency.UNLIMITED
