# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from dataclasses import dataclass
from typing import ClassVar

from instance_scheduler.ops_metrics import GatheringFrequency
from instance_scheduler.ops_metrics.metric_type.ops_metric import OpsMetric


@dataclass(frozen=True)
class CliRequestMetric(OpsMetric):
    command_used: str
    event_name: ClassVar[str] = "cli_request"
    collection_frequency: ClassVar[GatheringFrequency] = GatheringFrequency.UNLIMITED
