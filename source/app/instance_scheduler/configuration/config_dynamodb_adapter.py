# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from boto3.dynamodb.conditions import Key

from instance_scheduler import configuration
from instance_scheduler.util.dynamodb_utils import DynamoDBUtils


class ConfigDynamodbAdapter:
    """
    Adapter to load configuration from a DynamoDB storage type.
    """

    def __init__(self, tablename):
        self._tablename = tablename
        self._config = None

    @property
    def config(self):
        """
        Returns and cached the configuration data
        :return:
        """
        if self._config is None:
            self._config = self._get_config()
        return self._config

    def _get_config(self):
        dynamodb_table = DynamoDBUtils.get_dynamodb_table_resource_ref(self._tablename)

        resp = dynamodb_table.get_item(
            Key={"name": "scheduler", "type": "config"}, ConsistentRead=True
        )
        config = resp.get("Item", {})
        resp = dynamodb_table.query(KeyConditionExpression=Key("type").eq("period"))
        config[configuration.PERIODS] = resp.get("Items")
        resp = dynamodb_table.query(KeyConditionExpression=Key("type").eq("schedule"))
        config[configuration.SCHEDULES] = resp.get("Items")

        return config
