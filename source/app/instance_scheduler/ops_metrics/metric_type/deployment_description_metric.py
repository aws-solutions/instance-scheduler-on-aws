# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from dataclasses import dataclass
from typing import ClassVar

from instance_scheduler.ops_metrics import GatheringFrequency
from instance_scheduler.ops_metrics.metric_type.ops_metric import OpsMetric


@dataclass(frozen=True)
class DeploymentDescriptionMetric(OpsMetric):
    services: list[str]
    regions: list[str]
    num_accounts: int
    event_name: ClassVar[str] = "deployment_description"
    collection_frequency: ClassVar[GatheringFrequency] = GatheringFrequency.DAILY
