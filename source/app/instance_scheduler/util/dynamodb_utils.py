# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0


import boto3
from instance_scheduler import util


class DynamoDBUtils:
    @staticmethod
    def get_dynamodb_table_resource_ref(table_name):
        return boto3.resource("dynamodb", config=util.get_config()).Table(table_name)
