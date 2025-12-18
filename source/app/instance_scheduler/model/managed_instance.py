# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from abc import ABC
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional, TypedDict, cast

from instance_scheduler.scheduling.asg.asg_size import AsgSize
from instance_scheduler.scheduling.states import InstanceState
from instance_scheduler.util.arn import ARN
from instance_scheduler.util.validation import (
    validate_map_item,
    validate_number_item,
    validate_string_item,
)
from typing_extensions import override

if TYPE_CHECKING:
    from mypy_boto3_dynamodb.type_defs import AttributeValueTypeDef
else:
    AttributeValueTypeDef = object


@dataclass
class RegistryKey:
    account: str
    region: str
    service: str
    resource_type: str
    resource_id: str

    @property
    def sort_key(self) -> str:
        return f"resource#{self.region}#{self.service}#{self.resource_type}#{self.resource_id}"

    @classmethod
    def parse_db_sort_key(cls, account: str, sort_key: str) -> "RegistryKey":
        _, region, service, resource_type, resource_id = sort_key.split("#")

        return RegistryKey(
            account=account,
            region=region,
            service=service,
            resource_type=resource_type,
            resource_id=resource_id,
        )

    @classmethod
    def from_arn(cls, arn: ARN) -> "RegistryKey":
        return RegistryKey(
            account=arn.account,
            region=arn.region,
            service=arn.service,
            resource_type=arn.resource_type,
            resource_id=arn.resource_id,
        )

    def as_ddb_key(self) -> dict[str, AttributeValueTypeDef]:
        return {
            "account": {"S": self.account},
            "sk": {"S": self.sort_key},
        }


class CommonRegistryFields(TypedDict):
    account: str
    region: str
    resource_id: str
    arn: ARN
    schedule: str
    name: str
    stored_state: InstanceState


@dataclass
class RegisteredInstance(ABC):
    account: str
    region: str
    resource_id: str
    arn: ARN
    schedule: str
    name: str
    stored_state: InstanceState

    @property
    def key(self) -> RegistryKey:

        return RegistryKey(
            account=self.account,
            region=self.region,
            service=self.service,
            resource_type=self.resource_type,
            resource_id=self.resource_id,
        )

    @property
    def service(self) -> str:
        return self.arn.service

    @property
    def resource_type(self) -> str:
        return self.arn.resource_type

    @property
    def display_name(self) -> str:
        return f"{self.account}:{self.region}:{self.service}:{self.resource_id}"

    def to_item(self) -> dict[str, AttributeValueTypeDef]:
        return {
            "account": {"S": self.account},
            "sk": {"S": self.key.sort_key},
            "arn": {"S": self.arn},
            "schedule": {"S": self.schedule},
            "name": {"S": self.name},
            "state": {"S": self.stored_state},
        }

    @classmethod
    def _extract_common_fields(
        cls, item: dict[str, AttributeValueTypeDef]
    ) -> CommonRegistryFields:
        validate_string_item(item, "account", True)
        validate_string_item(item, "sk", True)
        validate_string_item(item, "arn", True)
        validate_string_item(item, "schedule", True)
        validate_string_item(item, "name", True)
        validate_string_item(item, "state", True)

        key = RegistryKey.parse_db_sort_key(item["account"]["S"], item["sk"]["S"])

        return {
            "account": key.account,
            "region": key.region,
            "resource_id": key.resource_id,
            "arn": ARN(item["arn"]["S"]),
            "schedule": item["schedule"]["S"],
            "name": item["name"]["S"],
            "stored_state": cast(InstanceState, item["state"]["S"]),
        }

    @classmethod
    def from_item(cls, item: dict[str, AttributeValueTypeDef]) -> "RegisteredInstance":
        validate_string_item(item, "account", True)
        validate_string_item(item, "sk", True)
        key = RegistryKey.parse_db_sort_key(item["account"]["S"], item["sk"]["S"])

        match key.service:
            case "ec2":
                return RegisteredEc2Instance.from_item(item)
            case "rds":
                return RegisteredRdsInstance.from_item(item)
            case "autoscaling":
                return RegisteredAsgInstance.from_item(item)
            case _:
                raise ValueError(f"Unknown service: {key.service}")


@dataclass
class RegisteredEc2Instance(RegisteredInstance):
    @classmethod
    def from_item(
        cls, item: dict[str, AttributeValueTypeDef]
    ) -> "RegisteredEc2Instance":
        common_fields = super()._extract_common_fields(item)

        return cls(**common_fields)


@dataclass
class RegisteredRdsInstance(RegisteredInstance):

    @property
    def is_cluster(self) -> bool:
        return ":cluster:" in self.arn

    @override
    def to_item(self) -> dict[str, AttributeValueTypeDef]:
        """Return this object as a dict suitable for a call to DynamoDB `put_item`"""
        return {
            **super().to_item(),
            "is_cluster": {"BOOL": self.is_cluster},
        }

    @classmethod
    def from_item(
        cls, item: dict[str, AttributeValueTypeDef]
    ) -> "RegisteredRdsInstance":
        common_fields = super()._extract_common_fields(item)

        return cls(
            **common_fields,
        )


@dataclass
class AsgConfiguration:
    last_updated: str
    min: int
    desired: int
    max: int
    schedule_hash: str
    valid_until: str

    @property
    def asg_size(self) -> AsgSize:
        return AsgSize(
            min_size=self.min,
            desired_size=self.desired,
            max_size=self.max,
        )

    def to_item(self) -> dict[str, AttributeValueTypeDef]:
        """Return this object as a dict suitable for a call to DynamoDB `put_item`"""
        return {
            "min": {"N": str(self.min)},
            "desired": {"N": str(self.desired)},
            "max": {"N": str(self.max)},
            "last_updated": {"S": self.last_updated},
            "schedule_hash": {"S": self.schedule_hash},
            "valid_until": {"S": self.valid_until},
        }

    @classmethod
    def from_item(cls, item: dict[str, AttributeValueTypeDef]) -> "AsgConfiguration":
        validate_string_item(item, "last_updated", True)
        validate_number_item(item, "min", True)
        validate_number_item(item, "desired", True)
        validate_number_item(item, "max", True)
        validate_string_item(item, "schedule_hash", True)
        validate_string_item(item, "valid_until", True)

        return cls(
            last_updated=item["last_updated"]["S"],
            min=int(item["min"]["N"]),
            desired=int(item["desired"]["N"]),
            max=int(item["max"]["N"]),
            schedule_hash=item["schedule_hash"]["S"],
            valid_until=item["valid_until"]["S"],
        )


@dataclass
class RegisteredAsgInstance(RegisteredInstance):
    last_configured: Optional[AsgConfiguration]

    def to_item(self) -> dict[str, AttributeValueTypeDef]:
        """Return this object as a dict suitable for a call to DynamoDB `put_item`"""
        item = super().to_item()
        if self.last_configured:
            item["last_configured"] = {"M": self.last_configured.to_item()}
        return item

    @classmethod
    def from_item(
        cls, item: dict[str, AttributeValueTypeDef]
    ) -> "RegisteredAsgInstance":
        common_fields = super()._extract_common_fields(item)

        last_configured = None
        if "last_configured" in item:
            validate_map_item(item, "last_configured", True)
            last_configured = AsgConfiguration.from_item(item["last_configured"]["M"])  # type: ignore

        return cls(
            **common_fields,
            last_configured=last_configured,
        )
