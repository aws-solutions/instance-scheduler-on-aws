# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

from dataclasses import dataclass
from typing import ClassVar

from instance_scheduler.ops_metrics import GatheringFrequency
from instance_scheduler.ops_metrics.metric_type.instance_count_metric import (
    InstanceCountMetric,
)


@dataclass(frozen=True)
class AsgCountMetric(InstanceCountMetric):
    collection_frequency: ClassVar[GatheringFrequency] = GatheringFrequency.UNLIMITED
