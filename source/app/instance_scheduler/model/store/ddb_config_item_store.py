# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from typing import Final

from botocore.exceptions import ClientError

from instance_scheduler.model.ddb_config_item import DdbConfigItem
from instance_scheduler.model.store.dynamo_client import hub_dynamo_client


class DdbConfigItemNotFound(Exception):
    pass


class DdbConfigItemStore:
    def __init__(
        self,
        table_name: str,
    ):
        self._table: Final = table_name

    def put(self, config_item: DdbConfigItem) -> None:
        """
        save this item to dynamo

        unlike the other stores, this will ALWAYS OVERWRITE because there is always exactly 1 DdbConfigItem
        saved in dynamo
        """
        hub_dynamo_client().put_item(
            TableName=self._table,
            Item=config_item.to_item(),
        )

    def get(self) -> DdbConfigItem:
        """fetch the DdbConfigItem from dynamo"""
        result = hub_dynamo_client().get_item(
            TableName=self._table,
            Key={"type": {"S": "config"}, "name": {"S": "scheduler"}},
        )

        if "Item" in result:
            return DdbConfigItem.from_item(result["Item"])
        else:
            raise DdbConfigItemNotFound(
                "scheduler config item not found in config table!"  # NOSONAR -- same error string is not duplication
            )

    def register_spoke_accounts(self, account_ids: set[str]) -> DdbConfigItem:
        """
        register spoke accounts for scheduling
        :returns the updated DdbConfigItem
        """
        result = hub_dynamo_client().update_item(
            TableName=self._table,
            Key={"type": {"S": "config"}, "name": {"S": "scheduler"}},
            UpdateExpression="add remote_account_ids :a",
            ExpressionAttributeValues={":a": {"SS": list(account_ids)}},
            ReturnValues="ALL_NEW",
        )

        if "Attributes" in result:
            return DdbConfigItem.from_item(result["Attributes"])
        else:
            raise DdbConfigItemNotFound(
                "scheduler config item not found in config table!"  # NOSONAR -- same error string is not duplication
            )

    def deregister_spoke_accounts(self, account_ids: set[str]) -> DdbConfigItem:
        """
        remove spoke accounts from scheduling
        :returns the updated DdbConfigItem
        """
        try:
            result = hub_dynamo_client().update_item(
                TableName=self._table,
                Key={"type": {"S": "config"}, "name": {"S": "scheduler"}},
                UpdateExpression="delete remote_account_ids :a",
                ExpressionAttributeValues={":a": {"SS": list(account_ids)}},
                ReturnValues="ALL_NEW",
            )

            if "Attributes" in result:
                return DdbConfigItem.from_item(result["Attributes"])
            else:
                raise DdbConfigItemNotFound(
                    "scheduler config item not found in config table!"  # NOSONAR -- same error string is not duplication
                )
        except ClientError as ce:
            if ce.response["Error"]["Code"] == "ValidationException":
                # this error can occur when the last spoke account was removed by this function as dynamo deletes the
                # "column" from the item entirely which causes the update expression to reference a field
                # that does not exist.
                pass  # swallow the error
            return self.get()
