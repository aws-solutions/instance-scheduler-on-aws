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

from requesthandlers.scheduler_ssm_handler import SchedulerSSMHandler
from configuration.scheduler_config_builder import SchedulerConfigBuilder
from unittest import mock
from unittest.mock import MagicMock
from os import environ
from contextlib import contextmanager
from util.logger import Logger
import datetime
from util.schedule_state import ScheduleState

table_name = environ['SCHEDULE_STATES_TABLE']

@contextmanager
def ddb_setup(dynamodb_client_resource):
    dynamodb_client_resource.create_table(
        TableName= table_name,
        KeySchema=[
            {"AttributeName": "name", "KeyType": "HASH"}
        ],
        AttributeDefinitions=[
            {
                "AttributeName": "name",
                "AttributeType": "S"
            }
        ],
        ProvisionedThroughput={
            "ReadCapacityUnits": 5,
            "WriteCapacityUnits": 5
        }
    )
    yield


def test_handler(dynamodb_client_resource, mocker):

    with ddb_setup(dynamodb_client_resource):
        LOG_STREAM = "{}-{:0>4d}{:0>2d}{:0>2d}"
        dt = datetime.datetime.utcnow()
        logstream = LOG_STREAM.format('test_configuration_module', dt.year, dt.month, dt.day)
        logger = Logger(logstream=logstream, buffersize=30, context={}, loggroup="test_configuration_module")
        config_data = {
            'regions': {'us-east-1'},
            'scheduled_services': {'ec2'},
            'stopped_tags': 'ScheduleMessage=Stopped on {year}/{month}/{day} at {hour}:{minute} {timezone}',
            'create_rds_snapshot': False,
            'default_timezone': 'US/Eastern',
            'trace': True,
            'started_tags': 'ScheduleMessage=Started on {year}/{month}/{day} at {hour}:{minute} {timezone}',
            'schedule_clusters': True,
            'name': 'scheduler',
            'tagname': 'Schedule',
            'type': 'config',
            'remote_account_ids':{'111111111111'},
            'periods': [
                {
                    'months': {'jan/3'},
                    'description': 'Every first monday of each quarter',
                    'weekdays': {'mon#1'},
                    'name': 'first-monday-in-quarter',
                    'type': 'period'
                },
                {
                    'begintime': '09:00',
                    'description': 'Office hours',
                    'endtime': '17:00',
                    'weekdays': {'mon-fri'},
                    'name': 'office-hours',
                    'type': 'period'
                },
                {
                    'endtime': '09:00',
                    'name': 'onlystop',
                    'type': 'period'
                },
                {
                    'endtime': '13:00',
                    'name': 'onlystop1',
                    'type': 'period'
                },
                {
                    'begintime': '09:00',
                    'endtime': '10:00',
                    'weekdays': {'mon-sun'},
                    'name': 'period1',
                    'type': 'period'
                },
                {
                    'begintime': '17:00',
                    'endtime': '18:00',
                    'weekdays': {'mon#4'},
                    'name': 'period2',
                    'type': 'period'
                },
                {
                    'begintime': '04:00',
                    'endtime': '07:00',
                    'weekdays': {'sat#4'},
                    'name': 'sat3',
                    'type': 'period'
                },
                {
                    'begintime': '12:00',
                    'endtime': '22:00',
                    'weekdays': {'sat#4'},
                    'name': 'sat4',
                    'type': 'period'
                },
                {
                    'begintime': '09:00',
                    'endtime': '10:50',
                    'weekdays': {'sun#4'},
                    'name': 'sun4',
                    'type': 'period'
                },
                {
                    'begintime': '15:00',
                    'endtime': '21:00',
                    'weekdays': {'sun#4'},
                    'name': 'sun4-2',
                    'type': 'period'
                },
                {
                    'begintime': '01:00',
                    'weekdays': {'fri-sat'},
                    'name': 'test1',
                    'type': 'period'
                },
                {
                    'begintime': '00:05',
                    'endtime': '01:05',
                    'weekdays': {'sat'},
                    'name': 'test12',
                    'type': 'period'
                },
                {
                    'begintime': '09:00',
                    'endtime': '12:00',
                    'weekdays': {'mon-fri'},
                    'name': 'test2',
                    'type': 'period'
                },
                {
                    'begintime': '11:00',
                    'endtime': '13:00',
                    'weekdays': {'mon-fri'},
                    'name': 'test3',
                    'type': 'period'
                },
                {
                    'begintime': '11:00',
                    'endtime': '15:00',
                    'weekdays': {'mon-fri'},
                    'name': 'test4',
                    'type': 'period'
                },
                {
                    'description': 'Days in weekend',
                    'weekdays': {'sat-sun'},
                    'name': 'weekends',
                    'type': 'period'
                },
                {
                    'description': 'Working days',
                    'weekdays': {'mon-fri'},
                    'name': 'working-days',
                    'type': 'period'
                }
            ],
            'schedules': [
                {
                    'timezone': 'US/Eastern',
                    'periods': {'period2', 'period1'},
                    'name': 'describe1',
                    'type': 'schedule'
                },
                {
                    'timezone': 'US/Eastern',
                    'periods': {'test4'},
                    'name': 'docDbSchedule',
                    'type': 'schedule'
                },
                {
                    'periods': {'onlystop1', 'onlystop'},
                    'name': 'onlystop', 'type': 'schedule'
                },
                {
                    'timezone': 'US/Eastern',
                    'description': 'Retain running',
                    'periods': {'office-hours'},
                    'name': 'running',
                    'type': 'schedule'
                },
                {
                    'timezone': 'UTC',
                    'description': 'Vertical scaling on weekdays, based on UTC time',
                    'periods': {'weekends@t2.nano', 'working-days@t2.micro'},
                    'name': 'scale-up-down',
                    'type': 'schedule'
                },
                {
                    'timezone': 'US/Pacific',
                    'description': 'Office hours in Seattle (Pacific)',
                    'periods': {'office-hours'},
                    'name': 'seattle-office-hours',
                    'type': 'schedule'
                },
                {
                    'description': 'Instances stopped',
                    'name': 'stopped',
                    'type': 'schedule'
                },
                {
                    'periods': {'test3'},
                    'name': 'test-error',
                    'type': 'schedule'
                },
                {
                    'timezone': 'US/Eastern',
                    'periods': {'sat3', 'sat4'},
                    'name': 'test-sat4',
                    'type': 'schedule'
                },
                {
                    'timezone': 'Asia/Macau',
                    'periods': {'test12', 'test1'},
                    'name': 'test-ssm1',
                    'type': 'schedule'
                },
                {
                    'periods': {'test1'},
                    'name': 'test-ssm2',
                    'type': 'schedule'
                },
                {
                    'description': 'Testing config sun#4',
                    'periods': {'sun4', 'sun4-2'},
                    'name': 'test-sun4',
                    'type': 'schedule'
                },
                {
                    'timezone': 'US/Eastern',
                    'periods': {'test1'},
                    'name': 'testMetrics',
                    'type': 'schedule'
                },
                {
                    'timezone': 'Europe/London',
                    'description': 'Office hours in UK',
                    'periods': {'office-hours'},
                    'name': 'uk-office-hours',
                    'type': 'schedule'
                }
            ]
        }
        response = SchedulerConfigBuilder(logger=logger).build(config_data)
        with mock.patch('configuration.get_scheduler_configuration', new_callable=mock.PropertyMock) as mock_configuration:
            mock_configuration.return_value = response
        
            with mock.patch('schedulers.ssm_handler.SSMHandler.run_ec2_instances_document', new_callable=mock.PropertyMock) as mock_ssm_response:
                mock_ssm_response.return_value = MagicMock(return_value="eeee")
                
                handler = SchedulerSSMHandler({}, {}, logger)
                handler.handle_request()

                schedulerStates = ScheduleState(logger, 'ec2')

                assert len(schedulerStates.get_all_schedules()) == 14


