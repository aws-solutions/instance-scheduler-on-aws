# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from abc import ABC
from dataclasses import dataclass
from typing import ClassVar

from instance_scheduler.ops_metrics import GatheringFrequency


@dataclass(frozen=True)
class OpsMetric(ABC):
    collection_frequency: ClassVar[GatheringFrequency] = GatheringFrequency.UNLIMITED
    event_name: ClassVar[str]
