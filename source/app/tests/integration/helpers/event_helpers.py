# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from contextlib import contextmanager
from typing import Any, Iterator
from unittest.mock import MagicMock

from instance_scheduler.util.session_manager import AssumedRole
from tests.integration.helpers.boto_client_helpers import mock_specific_client


def extract_events(mock_events_client: MagicMock) -> list[dict[str, Any]]:
    """Extract all events sent to event buses."""
    events = []
    for call in mock_events_client.put_events.call_args_list:
        events.extend(call.kwargs.get("Entries", []))
    return events


@contextmanager
def mock_events_client(region: str = "us-east-1") -> Iterator[MagicMock]:
    with mock_specific_client("events", region=region) as events_mock:
        events_mock.put_events = MagicMock()
        yield events_mock


def create_global_event_bus(role: AssumedRole) -> str:
    bus_name = "global-events"
    role.client("events").create_event_bus(Name=bus_name)
    return bus_name


def create_local_event_bus(role: AssumedRole) -> str:
    bus_name = "local-events"
    role.client("events").create_event_bus(Name=bus_name)
    return bus_name
