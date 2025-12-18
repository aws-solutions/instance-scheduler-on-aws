# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from typing import Final, Iterator, Literal, overload

from botocore.exceptions import ClientError
from instance_scheduler.model.managed_instance import (
    RegisteredAsgInstance,
    RegisteredEc2Instance,
    RegisteredInstance,
    RegisteredRdsInstance,
    RegistryKey,
)
from instance_scheduler.model.store.resource_registry import (
    ResourceAlreadyRegisteredException,
    ResourceRegistry,
    UnknownResourceException,
)
from instance_scheduler.observability.powertools_logging import powertools_logger
from instance_scheduler.util.session_manager import hub_dynamo_client

logger = powertools_logger()


class DynamoResourceRegistry(ResourceRegistry):
    def __init__(self, table_name: str):
        self._table: Final[str] = table_name

    def put(self, resource: RegisteredInstance, overwrite: bool = False) -> None:
        if overwrite:
            hub_dynamo_client().put_item(
                TableName=self._table,
                Item=resource.to_item(),
            )
        else:
            try:
                hub_dynamo_client().put_item(
                    TableName=self._table,
                    Item=resource.to_item(),
                    ConditionExpression="attribute_not_exists(#pk) AND attribute_not_exists(#sk)",
                    ExpressionAttributeNames={
                        "#pk": "account",
                        "#sk": "sk",
                    },
                )
            except ClientError as ce:
                if ce.response["Error"]["Code"] == "ConditionalCheckFailedException":
                    raise ResourceAlreadyRegisteredException(
                        f"resource '{resource.display_name}' already exists"
                    )
                else:
                    raise ce

    def get(self, key: RegistryKey) -> RegisteredInstance | None:
        try:
            response = hub_dynamo_client().get_item(
                TableName=self._table, Key=key.as_ddb_key()
            )
            if "Item" in response:
                return RegisteredInstance.from_item(response["Item"])
            return None
        except Exception as e:
            logger.warning(f"Error retrieving item: {e}", extra={"key": key})
            return None

    def delete(self, key: RegistryKey, error_if_missing: bool = False) -> None:
        if not error_if_missing:
            hub_dynamo_client().delete_item(TableName=self._table, Key=key.as_ddb_key())
        else:
            try:
                hub_dynamo_client().delete_item(
                    TableName=self._table,
                    Key=key.as_ddb_key(),
                    ConditionExpression="attribute_exists(#pk) AND attribute_exists(#sk)",
                    ExpressionAttributeNames={
                        "#pk": "account",
                        "#sk": "sk",
                    },
                )
            except ClientError as ce:
                if ce.response["Error"]["Code"] == "ConditionalCheckFailedException":
                    raise UnknownResourceException(f"resource ({key}) does not exist")
                else:
                    raise ce

    def find_all(self) -> Iterator[RegisteredInstance]:
        paginator = hub_dynamo_client().get_paginator("scan")
        for page in paginator.paginate(TableName=self._table):
            for item in page["Items"]:
                try:
                    yield RegisteredInstance.from_item(item)
                except Exception as e:
                    logger.warning(
                        f"Skipping malformed item: {e}", extra={"item": item}
                    )

    def find_by_account(self, account: str) -> Iterator[RegisteredInstance]:
        paginator = hub_dynamo_client().get_paginator("query")
        for page in paginator.paginate(
            TableName=self._table,
            KeyConditionExpression="account = :account",
            ExpressionAttributeValues={":account": {"S": account}},
        ):
            for item in page["Items"]:
                try:
                    yield RegisteredInstance.from_item(item)
                except Exception as e:
                    logger.warning(
                        f"Skipping malformed item: {e}", extra={"item": item}
                    )

    @overload
    def find_by_scheduling_target(
        self, account: str, region: str, service: Literal["ec2"]
    ) -> Iterator[RegisteredEc2Instance]: ...

    @overload
    def find_by_scheduling_target(
        self, account: str, region: str, service: Literal["rds"]
    ) -> Iterator[RegisteredRdsInstance]: ...

    @overload
    def find_by_scheduling_target(
        self, account: str, region: str, service: Literal["autoscaling"]
    ) -> Iterator[RegisteredAsgInstance]: ...

    @overload
    def find_by_scheduling_target(
        self, account: str, region: str, service: str
    ) -> Iterator[RegisteredInstance]: ...

    def find_by_scheduling_target(
        self, account: str, region: str, service: str
    ) -> Iterator[RegisteredInstance]:
        paginator = hub_dynamo_client().get_paginator("query")
        for page in paginator.paginate(
            TableName=self._table,
            KeyConditionExpression="account = :account AND begins_with(sk, :prefix)",
            ExpressionAttributeValues={
                ":account": {"S": account},
                ":prefix": {"S": f"resource#{region}#{service}#"},
            },
        ):
            for item in page["Items"]:
                try:
                    yield RegisteredInstance.from_item(item)
                except Exception as e:
                    logger.warning(
                        f"Skipping malformed item: {e}", extra={"item": item}
                    )
