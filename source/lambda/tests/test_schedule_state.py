######################################################################################################################
#  Copyright 2021 Amazon.com, Inc. or its affiliates. All Rights Reserved.                                           #
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


from contextlib import contextmanager
from util.schedule_state import ScheduleState
import datetime
from util.logger import Logger

from os import environ

table_name = environ['SCHEDULE_STATES_TABLE']

@contextmanager
def ddb_setup(dynamodb_client_resource):
    dynamodb_client_resource.create_table(
        TableName= table_name,
        KeySchema=[
            {"AttributeName": "name", "KeyType": "HASH"},
            {"AttributeName": "service", "KeyType": "HASH"}
        ],
        AttributeDefinitions=[
            {
                "AttributeName": "name",
                "AttributeType": "S"
            },{
                "AttributeName": "service",
                "AttributeType": "S"
            }
        ],
        ProvisionedThroughput={
            "ReadCapacityUnits": 5,
            "WriteCapacityUnits": 5
        }
    )
    yield

def test_scheduler_state(dynamodb_client_resource):

    with ddb_setup(dynamodb_client_resource):
        LOG_STREAM = "{}-{:0>4d}{:0>2d}{:0>2d}"
        dt = datetime.datetime.utcnow()
        logstream = LOG_STREAM.format(
            'test_configuration_module', dt.year, dt.month, dt.day)
        logger = Logger(logstream=logstream, buffersize=30,
                        context={}, loggroup="test_configuration_module")
        schedulerState = ScheduleState(logger, 'ec2')
        resp = schedulerState.get_schedule_state(None)

        assert resp.get("name") == None
        assert resp.get("state") == 'unknown'

        resp = schedulerState.save_schedule_state('test-schedule', 'running', '2021-07-09T09:00:01.953535-04:00', 'addd')

        resp = schedulerState.get_schedule_state('test-schedule')
        assert resp.get('state') == 'running'
        assert resp.get('name') == 'test-schedule'

        resp = schedulerState.save_schedule_state('test-schedule', 'stopped', '2021-07-09T17:00:00.000000-04:00', 'addd')

        resp = schedulerState.get_schedule_state('test-schedule')

        assert resp.get('state') == 'stopped'
        assert resp.get('name') == 'test-schedule'

        resp = schedulerState.get_all_schedules()

        assert len(resp) == 1
        for schedule_state in resp:
            assert schedule_state.get('name') ==  'test-schedule'
            assert schedule_state.get('state') ==  'stopped'

        resp = schedulerState.delete_schedule('test-schedule')

        resp = schedulerState.get_schedule_state('test-schedule')

        assert bool(resp) is False





