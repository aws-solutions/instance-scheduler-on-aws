# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from typing import Literal

UnknownState = Literal["unknown"]
AnyState = Literal["any"]
StoppedState = Literal["stopped"]
StoppedForResizeState = Literal["stopped_for_resize"]
RunningState = Literal["running"]
RetainRunningState = Literal["retain-running"]

ScheduleState = (
    UnknownState
    | AnyState
    | StoppedState
    | StoppedForResizeState
    | RunningState
    | RetainRunningState
)
