# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Iterable, Optional

from instance_scheduler.scheduling.scheduling_decision import (
    ManagedInstance,
)
from instance_scheduler.scheduling.scheduling_result import (
    SchedulingAction,
    SchedulingResult,
)

if TYPE_CHECKING:
    from mypy_boto3_events.type_defs import PutEventsRequestEntryTypeDef
else:
    PutEventsRequestEntryTypeDef = object


@dataclass
class SchedulingEvent:
    account: str
    region: str
    service: str
    resource_id: str
    arn: str
    schedule: str
    requested_action: Optional[str]
    action_taken: Optional[str]

    @classmethod
    def from_result(
        cls, result: SchedulingResult[ManagedInstance]
    ) -> "SchedulingEvent":
        return cls(
            account=result.instance.registry_info.account,
            region=result.instance.registry_info.region,
            service=result.instance.registry_info.service,
            resource_id=result.instance.registry_info.resource_id,
            arn=result.instance.registry_info.arn,
            schedule=result.instance.registry_info.schedule,
            requested_action=(
                result.requested_action.value if result.requested_action else None
            ),
            action_taken=result.action_taken.value if result.action_taken else None,
        )

    @classmethod
    def stream_results_from_scheduling_summary(
        cls, results: Iterable[SchedulingResult[ManagedInstance]]
    ) -> Iterable["SchedulingEvent"]:
        return (
            SchedulingEvent.from_result(result)
            for result in results
            if result.action_taken != SchedulingAction.DO_NOTHING
        )

    def as_event_bus_event(self) -> PutEventsRequestEntryTypeDef:
        return {
            "Source": "instance-scheduler",
            "DetailType": "Scheduling Action",
            "Resources": [self.arn],
            "Detail": json.dumps(
                {
                    "account": self.account,
                    "region": self.region,
                    "service": self.service,
                    "resource_id": self.resource_id,
                    "requested_action": self.requested_action,
                    "action_taken": self.action_taken or "None",
                    "schedule": self.schedule,
                }
            ),
        }
