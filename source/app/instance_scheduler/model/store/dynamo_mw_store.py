# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from collections.abc import Iterator
from typing import Final

from instance_scheduler.model import MWStore
from instance_scheduler.model.maint_win import EC2SSMMaintenanceWindow
from instance_scheduler.model.store.dynamo_client import hub_dynamo_client


class DynamoMWStore(MWStore):
    def __init__(self, table_name: str) -> None:
        self._table_name: Final = table_name

    def put(self, window: EC2SSMMaintenanceWindow) -> None:
        hub_dynamo_client().put_item(TableName=self._table_name, Item=window.to_item())

    def delete(self, window: EC2SSMMaintenanceWindow) -> None:
        hub_dynamo_client().delete_item(TableName=self._table_name, Key=window.to_key())

    def find_by_account_region(
        self, account: str, region: str
    ) -> Iterator[EC2SSMMaintenanceWindow]:
        primary_key: Final = f"{account}:{region}"
        paginator: Final = hub_dynamo_client().get_paginator("query")
        for page in paginator.paginate(
            TableName=self._table_name,
            ExpressionAttributeNames={"#pk": "account-region"},
            ExpressionAttributeValues={":val": {"S": primary_key}},
            KeyConditionExpression="#pk = :val",
        ):
            for item in page["Items"]:
                yield EC2SSMMaintenanceWindow.from_item(item)
