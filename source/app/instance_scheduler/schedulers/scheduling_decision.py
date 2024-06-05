# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import dataclasses
from enum import Enum
from typing import Optional

from instance_scheduler.schedulers.states import InstanceState
from instance_scheduler.service.abstract_instance import AbstractInstance


class SchedulingAction(Enum):
    DO_NOTHING = None
    START = "start"
    STOP = "stop"


@dataclasses.dataclass
class SchedulingDecision:
    instance: AbstractInstance
    action: SchedulingAction
    new_state_table_state: Optional[InstanceState]
    reason: str
    desired_size: Optional[str] = None
