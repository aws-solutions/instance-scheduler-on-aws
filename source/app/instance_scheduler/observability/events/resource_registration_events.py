# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

from instance_scheduler.model.managed_instance import RegisteredInstance

if TYPE_CHECKING:
    from mypy_boto3_events.type_defs import PutEventsRequestEntryTypeDef
else:
    PutEventsRequestEntryTypeDef = object


@dataclass
class ResourceRegistrationEvent:
    account: str
    region: str
    service: str
    resource_id: str
    arn: str
    schedule: str

    @classmethod
    def for_resource(cls, resource: RegisteredInstance) -> "ResourceRegistrationEvent":
        return ResourceRegistrationEvent(
            account=resource.account,
            region=resource.region,
            service=resource.service,
            resource_id=resource.resource_id,
            arn=resource.arn,
            schedule=resource.schedule,
        )

    def as_event_bus_event(self) -> PutEventsRequestEntryTypeDef:
        return {
            "Source": "instance-scheduler",
            "DetailType": "Resource Registered",
            "Resources": [self.arn],
            "Detail": json.dumps(
                {
                    "account": self.account,
                    "region": self.region,
                    "service": self.service,
                    "resource_id": self.resource_id,
                    "schedule": self.schedule,
                }
            ),
        }


@dataclass
class ResourceDeregistrationEvent:
    account: str
    region: str
    service: str
    arn: str
    resource_id: str
    schedule: str

    def as_event_bus_event(self) -> PutEventsRequestEntryTypeDef:
        return {
            "Source": "instance-scheduler",
            "DetailType": "Resource Deregistered",
            "Resources": [self.arn],
            "Detail": json.dumps(
                {
                    "account": self.account,
                    "region": self.region,
                    "service": self.service,
                    "resource_id": self.resource_id,
                    "schedule": self.schedule,
                }
            ),
        }
