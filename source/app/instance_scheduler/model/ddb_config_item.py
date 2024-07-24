# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from instance_scheduler.model.ddb_item_utils import skip_if_empty

if TYPE_CHECKING:
    from mypy_boto3_dynamodb.type_defs import AttributeValueTypeDef
else:
    AttributeValueTypeDef = object


@dataclass
class DdbConfigItem:
    """
    object representation of the config item stored in the dynamodb config table

    There can only ever be 1 config item stored in dynamodb as this item represents the global configuration
    data of the solution that may be updated dynamically (is not stored in the lambda environment)
    """

    organization_id: str = ""
    remote_account_ids: list[str] = field(default_factory=list)

    def to_item(self) -> dict[str, AttributeValueTypeDef]:
        """Return this object as a dict suitable for a call to DynamoDB `put_item`"""
        return {
            "type": {"S": "config"},
            "name": {"S": "scheduler"},
            "organization_id": {"S": self.organization_id},
            **skip_if_empty("remote_account_ids", {"SS": self.remote_account_ids}),
        }

    @classmethod
    def from_item(cls, item: dict[str, AttributeValueTypeDef]) -> "DdbConfigItem":
        return DdbConfigItem(
            organization_id=item.get("organization_id", {}).get("S", ""),
            remote_account_ids=list(item.get("remote_account_ids", {}).get("SS", [])),
        )
