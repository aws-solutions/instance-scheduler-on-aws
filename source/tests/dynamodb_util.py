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
from datetime import datetime, timedelta
from functools import lru_cache

@lru_cache(maxsize=1)
def get_ddb_resource():
    return boto3.resource("dynamodb")

@lru_cache(maxsize=1)
def get_config_table(config_table_id):
    try:
        return get_ddb_resource().Table(config_table_id)
    except Exception as e:
        print('Failed to get ConfigTable details. Exception: {}'.format(e))
        return None

def setup_schedule_config(config_table):
    '''
    Setup ConfigTable for testing. Check if required <schedule> item exists in ddb. If not, put an item.
    '''
    res = config_table.get_item(
        Key={
            'type': "schedule",
            'name': "test-schedule"
        }
    )

    if 'Item' in res:
        print('schedule tag config found')
    else:
        print('schedule tag config not found. Adding config...')
        config_table.put_item(
            Item={
                "type": "schedule",
                "name": "test-schedule",
                "periods": {
                    "test-period"
                },
                "timezone": "UTC",
            }
        )

def setup_period_config(config_table):
    '''
    Setup ConfigTable for testing. Check if required <period> item exists in ddb. If not, put an item.
    '''
    res = config_table.get_item(
        Key={
            'type': "period",
            'name': "test-period"
        }
    )

    if 'Item' in res:
        print('period config found')
    else:
        print('period config not found. Adding config...')
        config_table.put_item(
            Item={
                "type": "period",
                "name": "test-period",
                "begintime": "00:00",
                "endtime": "23:59",
                "weekdays": {
                    'mon-sun'
                }
            }
        )

def update_period_config(config_table):
    current_time = datetime.utcnow()
    begin_time = current_time + timedelta(minutes=2)
    end_time = current_time + timedelta(minutes=4)

    begin_time_val = f'{begin_time.hour}:{begin_time.minute}'
    end_time_val = f'{end_time.hour}:{end_time.minute}'

    print(f"setting begintime to {begin_time_val} and endtime to {end_time_val}")

    try:
        config_table.update_item(
            Key={
                "type": "period",
                "name": "test-period"
            },
            UpdateExpression="SET begintime = :bt, endtime = :et",
            ExpressionAttributeValues= {
                ":bt": begin_time_val,
                ":et": end_time_val
            }
        )
    except Exception as e:
        print(f"Failed to update period. Exception: {e}")
