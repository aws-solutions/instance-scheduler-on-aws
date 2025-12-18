# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from typing import Protocol


class EventsEnv(Protocol):
    local_event_bus_name: str
    global_event_bus_name: str
