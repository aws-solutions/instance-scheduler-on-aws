# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from typing import TYPE_CHECKING, Optional

import boto3

from instance_scheduler.util import get_boto_config

if TYPE_CHECKING:
    from mypy_boto3_dynamodb import DynamoDBClient
else:
    DynamoDBClient = object


# shared dynamodb client to minimize the number of KMS api calls needed to access encrypted dynamodb tables
# note: KMS caching with dynamo is done on a per-connection (client) level
_hub_dynamo_client: Optional[DynamoDBClient] = None


def hub_dynamo_client() -> DynamoDBClient:
    global _hub_dynamo_client
    if not _hub_dynamo_client:
        new_client: DynamoDBClient = boto3.client("dynamodb", config=get_boto_config())
        _hub_dynamo_client = new_client
    return _hub_dynamo_client
