# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from typing import Optional, TypedDict

from typing_extensions import NotRequired

from instance_scheduler.configuration.running_period import RunningPeriod


class RunningPeriodDictElement(TypedDict):
    period: RunningPeriod
    instancetype: NotRequired[Optional[str]]
