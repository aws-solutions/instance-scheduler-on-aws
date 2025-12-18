# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

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
