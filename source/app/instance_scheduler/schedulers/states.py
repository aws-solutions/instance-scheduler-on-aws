# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from enum import Enum
from typing import Optional, TypeGuard


class ScheduleState(str, Enum):
    """possible desired states from a Schedule"""

    RUNNING = "running"
    ANY = "any"
    STOPPED = "stopped"


class InstanceState(str, Enum):
    """additional states used for scheduling that can be saved to a specific instance"""

    RUNNING = "running"
    ANY = "any"
    STOPPED = "stopped"
    UNKNOWN = "unknown"
    STOPPED_FOR_RESIZE = "stopped_for_resize"
    RETAIN_RUNNING = "retain-running"
    START_FAILED = "start_failed"


def is_valid_instance_state(value: Optional[str]) -> TypeGuard[InstanceState]:
    return any(value == state for state in InstanceState)
