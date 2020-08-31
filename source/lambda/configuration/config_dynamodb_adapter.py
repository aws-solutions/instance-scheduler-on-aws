######################################################################################################################
#  Copyright 2019 Amazon.com, Inc. or its affiliates. All Rights Reserved.                                           #
#                                                                                                                    #
#  Licensed under the Apache License Version 2.0 (the "License"). You may not use this file except in compliance     #
#  with the License. A copy of the License is located at                                                             #
#                                                                                                                    #
#      http://www.apache.org/licenses/                                                                               #
#                                                                                                                    #
#  or in the "license" file accompanying this file. This file is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES #
#  OR CONDITIONS OF ANY KIND, express or implied. See the License for the specific language governing permissions    #
#  and limitations under the License.                                                                                #
######################################################################################################################

import boto3
from boto3.dynamodb.conditions import Key

import configuration


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

        dynamodb = boto3.resource("dynamodb")
        dynamodb_table = dynamodb.Table(self._tablename)

        resp = dynamodb_table.get_item(Key={"name": "scheduler", "type": "config"}, ConsistentRead=True)
        config = resp.get("Item", {})
        resp = dynamodb_table.query(KeyConditionExpression=Key("type").eq('period'))
        config[configuration.PERIODS] = resp.get("Items")
        resp = dynamodb_table.query(KeyConditionExpression=Key("type").eq('schedule'))
        config[configuration.SCHEDULES] = resp.get("Items")

        return config
