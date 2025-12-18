# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from itertools import batched
from typing import TYPE_CHECKING, Any, Iterable, Optional

from instance_scheduler.observability.events.events_environment import EventsEnv
from instance_scheduler.observability.events.scheduling_events import SchedulingEvent
from instance_scheduler.scheduling.scheduling_decision import (
    ManagedInstance,
)
from instance_scheduler.scheduling.scheduling_result import (
    SchedulingAction,
    SchedulingResult,
)
from instance_scheduler.util.session_manager import AssumedRole, lambda_execution_role

if TYPE_CHECKING:
    from mypy_boto3_events.type_defs import PutEventsRequestEntryTypeDef
else:
    PutEventsRequestEntryTypeDef = object


class EventsBuffer:
    BUFFER_LENGTH = 10

    def __init__(self, scheduling_role: AssumedRole, env: EventsEnv) -> None:
        self.buffer: list[PutEventsRequestEntryTypeDef] = []
        self.scheduling_role = scheduling_role
        self.env = env

    def __enter__(self) -> "EventsBuffer":
        return self

    def __exit__(
        self,
        exc_type: Optional[type],
        exc_val: Optional[Exception],
        exc_tb: Optional[Any],
    ) -> None:
        self.flush()

    def push(self, event: PutEventsRequestEntryTypeDef) -> None:
        self.buffer.append(event)
        if len(self.buffer) >= self.BUFFER_LENGTH:
            self.flush()

    def flush(self) -> None:
        if self.buffer:
            send_events_to_local_and_global_buses(
                self.buffer, self.scheduling_role, self.env
            )
            self.buffer.clear()


def report_scheduling_results_to_eventbus(
    results: Iterable[SchedulingResult[ManagedInstance]],
    scheduling_role: AssumedRole,
    env: EventsEnv,
) -> None:
    events = (
        SchedulingEvent.from_result(result).as_event_bus_event()
        for result in results
        if result.action_taken != SchedulingAction.DO_NOTHING
    )

    send_events_to_local_and_global_buses(events, scheduling_role, env)


def send_events_to_local_and_global_buses(
    events: Iterable[PutEventsRequestEntryTypeDef],
    scheduling_role: AssumedRole,
    env: EventsEnv,
) -> None:
    for batch in batched(events, 10):
        scheduling_role.client("events").put_events(
            Entries=[
                {
                    **event,
                    "EventBusName": env.local_event_bus_name,
                }
                for event in batch
            ]
        )
        lambda_execution_role().client("events").put_events(
            Entries=[
                {
                    **event,
                    "EventBusName": env.global_event_bus_name,
                }
                for event in batch
            ]
        )
