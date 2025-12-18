# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from abc import ABC
from dataclasses import dataclass
from typing import ClassVar


@dataclass(frozen=True)
class OpsMetric(ABC):
    event_name: ClassVar[str]
    context_version: ClassVar[int]
