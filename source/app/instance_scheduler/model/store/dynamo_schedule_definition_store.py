# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import json
from collections.abc import Mapping
from typing import TYPE_CHECKING, Final, Optional, Sequence

from botocore.exceptions import ClientError

from instance_scheduler.model.schedule_definition import (
    InvalidScheduleDefinition,
    ScheduleDefinition,
)
from instance_scheduler.model.store.ddb_transact_write import WriteTransaction
from instance_scheduler.model.store.dynamo_client import hub_dynamo_client
from instance_scheduler.model.store.schedule_definition_store import (
    ScheduleAlreadyExistsException,
    ScheduleDefinitionStore,
    UnknownScheduleException,
)

if TYPE_CHECKING:
    from mypy_boto3_dynamodb.type_defs import TransactWriteItemTypeDef
else:
    TransactWriteItemTypeDef = object


class DynamoScheduleDefinitionStore(ScheduleDefinitionStore):
    def __init__(
        self,
        table_name: str,
    ):
        self._table: Final = table_name

    def put(self, schedule: ScheduleDefinition, overwrite: bool = False) -> None:
        if overwrite:
            hub_dynamo_client().put_item(
                TableName=self._table,
                Item=schedule.to_item(),
            )
        else:
            try:
                hub_dynamo_client().put_item(
                    TableName=self._table,
                    Item=schedule.to_item(),
                    ConditionExpression=(
                        "attribute_exists(#key_type) AND attribute_exists(#key_name)"  # NOSONAR -- this is not duplication
                        if overwrite
                        else "attribute_not_exists(#key_type) AND attribute_not_exists(#key_name)"
                    ),
                    ExpressionAttributeNames={
                        "#key_type": "type",  # NOSONAR -- this is not duplication
                        "#key_name": "name",  # NOSONAR -- this is not duplication
                    },
                )
            except ClientError as ce:
                if ce.response["Error"]["Code"] == "ConditionalCheckFailedException":
                    raise ScheduleAlreadyExistsException(
                        f"schedule {schedule.name} already exists"
                    )
                else:
                    raise ce

    def delete(self, schedule_name: str, error_if_missing: bool = False) -> None:
        if error_if_missing:
            try:
                hub_dynamo_client().delete_item(
                    TableName=self._table,
                    Key={"type": {"S": "schedule"}, "name": {"S": schedule_name}},
                    ConditionExpression="attribute_exists(#key_type) AND attribute_exists(#key_name)",
                    ExpressionAttributeNames={
                        "#key_type": "type",  # NOSONAR -- this is not duplication
                        "#key_name": "name",  # NOSONAR -- this is not duplication
                    },
                )
            except ClientError as ce:
                if ce.response["Error"]["Code"] == "ConditionalCheckFailedException":
                    raise UnknownScheduleException(
                        f"schedule {schedule_name} does not exist"
                    )
                else:
                    raise ce
        else:
            hub_dynamo_client().delete_item(
                TableName=self._table,
                Key={"type": {"S": "schedule"}, "name": {"S": schedule_name}},
            )

    def transact_put(
        self, schedule: ScheduleDefinition, overwrite: bool = False
    ) -> Sequence[TransactWriteItemTypeDef]:
        if overwrite:
            return [
                {
                    "Put": {
                        "Item": schedule.to_item(),
                        "TableName": self._table,
                    }
                }
            ]
        else:
            return [
                {
                    "Put": {
                        "Item": schedule.to_item(),
                        "TableName": self._table,
                        "ConditionExpression": "attribute_not_exists(#key_type) AND attribute_not_exists(#key_name)",
                        "ExpressionAttributeNames": {
                            "#key_type": "type",  # NOSONAR -- this is not duplication
                            "#key_name": "name",  # NOSONAR -- this is not duplication
                        },
                    }
                }
            ]

    def transact_delete(
        self, schedule_name: str, error_if_missing: bool = False
    ) -> Sequence[TransactWriteItemTypeDef]:
        if error_if_missing:
            return [
                {
                    "Delete": {
                        "Key": {
                            "type": {"S": "schedule"},
                            "name": {"S": schedule_name},
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
                            "type": {"S": "schedule"},
                            "name": {"S": schedule_name},
                        },
                        "TableName": self._table,
                    }
                }
            ]

    def find_by_name(self, schedule_name: str) -> Optional[ScheduleDefinition]:
        result = hub_dynamo_client().get_item(
            TableName=self._table,
            Key={"type": {"S": "schedule"}, "name": {"S": schedule_name}},
        )

        if "Item" in result:
            try:
                return ScheduleDefinition.from_item(result["Item"])
            except InvalidScheduleDefinition as e:
                raise InvalidScheduleDefinition(
                    f"Unable to build schedule {schedule_name}: {e}"
                )
        else:
            return None

    def find_by_period(self, period_name: str) -> Mapping[str, ScheduleDefinition]:
        """
        find all schedules that reference the provided period
        """

        def contains_period(sched_def: ScheduleDefinition, period_name: str) -> bool:
            for period_identifier in sched_def.periods:
                if period_identifier.name == period_name:
                    return True
            return False

        schedules = self.find_all()
        return {
            sched_name: sched_def
            for sched_name, sched_def in schedules.items()
            if contains_period(sched_def, period_name)
        }

    def find_all(self) -> Mapping[str, ScheduleDefinition]:
        result, errors = self.find_all_with_errors()
        return result

    def find_all_with_errors(
        self,
    ) -> tuple[Mapping[str, ScheduleDefinition], list[InvalidScheduleDefinition]]:
        result = hub_dynamo_client().query(
            TableName=self._table,
            KeyConditionExpression="#part_key=:value",
            ExpressionAttributeNames={"#part_key": "type"},
            ExpressionAttributeValues={":value": {"S": "schedule"}},
        )

        schedules: dict[str, ScheduleDefinition] = {}
        exceptions: list[InvalidScheduleDefinition] = list()
        for item in result["Items"]:
            try:
                schedule = ScheduleDefinition.from_item(item)
                schedules[schedule.name] = schedule
            except InvalidScheduleDefinition as e:
                exceptions.append(
                    InvalidScheduleDefinition(
                        f"Invalid Schedule Definition:\n{json.dumps(item, indent=2)}\n{e}"
                    )
                )

        return schedules, exceptions

    @staticmethod
    def new_transaction() -> WriteTransaction:
        return WriteTransaction(hub_dynamo_client())
