# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from dataclasses import dataclass

from instance_scheduler.ops_metrics.metric_type.ops_metric import OpsMetric


@dataclass(frozen=True)
class AnonymousMetricWrapper:
    timestamp: str
    uuid: str
    solution: str
    version: str
    event_name: str
    context_version: int
    context: OpsMetric
