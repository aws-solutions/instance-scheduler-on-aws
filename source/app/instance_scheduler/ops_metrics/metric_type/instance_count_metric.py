# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from dataclasses import dataclass
from typing import ClassVar

from instance_scheduler.ops_metrics import GatheringFrequency
from instance_scheduler.ops_metrics.metric_type.ops_metric import OpsMetric


@dataclass(frozen=True)
class InstanceCountMetric(OpsMetric):
    service: str
    region: str
    num_instances: int
    num_schedules: int
    event_name: ClassVar[str] = "instance_count"
    collection_frequency: ClassVar[GatheringFrequency] = GatheringFrequency.DAILY
