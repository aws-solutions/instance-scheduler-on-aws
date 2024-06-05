# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from typing import NotRequired, Optional, TypedDict

from instance_scheduler.configuration.running_period import RunningPeriod


class RunningPeriodDictElement(TypedDict):
    period: RunningPeriod
    instancetype: NotRequired[Optional[str]]
