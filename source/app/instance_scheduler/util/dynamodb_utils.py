# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from typing import TYPE_CHECKING, Any

import boto3

from instance_scheduler.util import get_boto_config

if TYPE_CHECKING:
    from mypy_boto3_dynamodb.service_resource import Table
else:
    Table = object


class DynamoDBUtils:
    @staticmethod
    def get_dynamodb_table_resource_ref(
        table_name: str,
    ) -> Any:  # todo: switch typing to "Table"
        table: Table = boto3.resource("dynamodb", config=get_boto_config()).Table(
            table_name
        )
        return table
