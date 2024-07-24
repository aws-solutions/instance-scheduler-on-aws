# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, ClassVar

from instance_scheduler.ops_metrics import GatheringFrequency
from instance_scheduler.ops_metrics.metric_type.ops_metric import OpsMetric
from instance_scheduler.ops_monitoring.instance_counts import ServiceInstanceCounts

if TYPE_CHECKING:
    from mypy_boto3_cloudwatch.literals import StandardUnitType
    from mypy_boto3_cloudwatch.type_defs import MetricDatumTypeDef
else:
    MetricDatumTypeDef = object
    StandardUnitType = object


@dataclass(frozen=True)
class Dimension:
    name: str
    value: str


@dataclass(frozen=True)
class MetricDataItem:
    metric_name: str
    dimensions: list[Dimension]
    timestamp: datetime
    value: float
    unit: StandardUnitType

    def to_cloudwatch_data(self) -> MetricDatumTypeDef:
        return {
            "MetricName": self.metric_name,
            "Dimensions": [
                {"Name": dimension.name, "Value": dimension.value}
                for dimension in self.dimensions
            ],
            "Timestamp": self.timestamp,
            "Value": self.value,
            "Unit": self.unit,
        }


@dataclass(frozen=True)
class InsightsMetric(OpsMetric):
    metric_data: list[MetricDataItem]
    event_name: ClassVar[str] = "insights_metric"
    collection_frequency: ClassVar[GatheringFrequency] = GatheringFrequency.UNLIMITED
    context_version: ClassVar[int] = 1

    @classmethod
    def from_service_counts(
        cls, service_counts: ServiceInstanceCounts, scheduling_interval_minutes: int
    ) -> "InsightsMetric":
        # imported here to avoid circular import
        from instance_scheduler.ops_monitoring.cw_ops_insights import (
            CloudWatchOperationalInsights,
        )

        return InsightsMetric(
            metric_data=CloudWatchOperationalInsights.build_per_instance_type_metrics(
                service_counts, scheduling_interval_minutes=scheduling_interval_minutes
            ),
        )
