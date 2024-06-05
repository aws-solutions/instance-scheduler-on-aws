# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import json
from collections.abc import Mapping
from typing import TYPE_CHECKING, Final, Optional, Sequence

from botocore.exceptions import ClientError

from instance_scheduler.model.period_definition import (
    InvalidPeriodDefinition,
    PeriodDefinition,
)
from instance_scheduler.model.store.dynamo_client import hub_dynamo_client
from instance_scheduler.model.store.period_definition_store import (
    PeriodAlreadyExistsException,
    PeriodDefinitionStore,
    UnknownPeriodException,
)

if TYPE_CHECKING:
    from mypy_boto3_dynamodb.type_defs import TransactWriteItemTypeDef
else:
    TransactWriteItemTypeDef = object


class DynamoPeriodDefinitionStore(PeriodDefinitionStore):
    def __init__(self, table_name: str):
        self._table: Final[str] = table_name

    def put(self, period: PeriodDefinition, overwrite: bool = False) -> None:
        if overwrite:
            hub_dynamo_client().put_item(
                TableName=self._table,
                Item=period.to_item(),
            )
        else:
            try:
                hub_dynamo_client().put_item(
                    TableName=self._table,
                    Item=period.to_item(),
                    ConditionExpression="attribute_not_exists(#key_type) AND attribute_not_exists(#key_name)",
                    ExpressionAttributeNames={
                        "#key_type": "type",  # NOSONAR -- this is not duplication
                        "#key_name": "name",  # NOSONAR -- this is not duplication
                    },
                )
            except ClientError as ce:
                if ce.response["Error"]["Code"] == "ConditionalCheckFailedException":
                    raise PeriodAlreadyExistsException(
                        f"period {period.name} already exists"
                    )
                else:
                    raise ce

    def delete(self, period_name: str, error_if_missing: bool = False) -> None:
        if error_if_missing:
            try:
                hub_dynamo_client().delete_item(
                    TableName=self._table,
                    Key={"type": {"S": "period"}, "name": {"S": period_name}},
                    ConditionExpression="attribute_exists(#key_type) AND attribute_exists(#key_name)",
                    ExpressionAttributeNames={
                        "#key_type": "type",  # NOSONAR -- this is not duplication
                        "#key_name": "name",  # NOSONAR -- this is not duplication
                    },
                )
            except ClientError as ce:
                if ce.response["Error"]["Code"] == "ConditionalCheckFailedException":
                    raise UnknownPeriodException(f"period {period_name} does not exist")
                else:
                    raise ce
        else:
            hub_dynamo_client().delete_item(
                TableName=self._table,
                Key={"type": {"S": "period"}, "name": {"S": period_name}},
            )

    def transact_put(
        self, period: PeriodDefinition, overwrite: bool = False
    ) -> Sequence[TransactWriteItemTypeDef]:
        if overwrite:
            return [
                {
                    "Put": {
                        "Item": period.to_item(),
                        "TableName": self._table,
                    }
                }
            ]
        else:
            return [
                {
                    "Put": {
                        "Item": period.to_item(),
                        "TableName": self._table,
                        "ConditionExpression": "attribute_not_exists(#key_type) AND attribute_not_exists(#key_name)",
                        "ExpressionAttributeNames": {
                            "#key_type": "type",  # NOSONAR -- this is not duplication
                            "#key_name": "name",  # NOSONAR -- this is not duplication
                        },
                    },
                }
            ]

    def transact_delete(
        self, period_name: str, error_if_missing: bool = False
    ) -> Sequence[TransactWriteItemTypeDef]:
        if error_if_missing:
            return [
                {
                    "Delete": {
                        "Key": {
                            "type": {"S": "period"},
                            "name": {"S": period_name},
                        },
                        "TableName": self._table,
                        "ConditionExpression": "attribute_exists(#key_type) AND attribute_exists(#key_name)",
                        "ExpressionAttributeNames": {
                            "#key_type": "type",  # NOSONAR -- this is not duplication
                            "#key_name": "name",  # NOSONAR -- this is not duplication
                        },
                    }
                }
            ]
        else:
            return [
                {
                    "Delete": {
                        "Key": {
                            "type": {"S": "period"},
                            "name": {"S": period_name},
                        },
                        "TableName": self._table,
                    }
                }
            ]

    def find_by_name(self, period_name: str) -> Optional[PeriodDefinition]:
        result = hub_dynamo_client().get_item(
            TableName=self._table,
            Key={"type": {"S": "period"}, "name": {"S": period_name}},
        )

        if "Item" in result:
            try:
                return PeriodDefinition.from_item(result["Item"])
            except InvalidPeriodDefinition as e:
                raise InvalidPeriodDefinition(
                    f"Unable to build period {period_name}: {e}"
                )
        else:
            return None

    def find_all(self) -> Mapping[str, PeriodDefinition]:
        result, errors = self.find_all_with_errors()
        return result

    def find_all_with_errors(
        self,
    ) -> tuple[Mapping[str, PeriodDefinition], list[InvalidPeriodDefinition]]:
        result = hub_dynamo_client().query(
            TableName=self._table,
            KeyConditionExpression="#part_key=:value",
            ExpressionAttributeNames={"#part_key": "type"},
            ExpressionAttributeValues={":value": {"S": "period"}},
        )

        periods: dict[str, PeriodDefinition] = {}
        exceptions: list[InvalidPeriodDefinition] = list()
        for item in result["Items"]:
            try:
                period = PeriodDefinition.from_item(item)
                periods[period.name] = period
            except InvalidPeriodDefinition as e:
                exceptions.append(
                    InvalidPeriodDefinition(
                        f"Invalid Period Definition\n{json.dumps(item, indent=2)}\n{e}"
                    )
                )

        return periods, exceptions
