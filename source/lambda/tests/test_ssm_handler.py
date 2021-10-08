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


from schedulers.ssm_handler import SSMHandler
from util.logger import Logger
import datetime
from unittest.mock import call
#import schedulers

def get_logger():
    LOG_STREAM = "{}-{:0>4d}{:0>2d}{:0>2d}"
    dt = datetime.datetime.utcnow()
    logstream = LOG_STREAM.format('test_configuration_module', dt.year, dt.month, dt.day)
    return Logger(logstream=logstream, buffersize=30, context={}, loggroup="test_configuration_module")

def test_run_ssm_runbook_with_multiple_of_max_accounts(mocker):
    handler = SSMHandler(
        accounts=[0,1,2,3,4,5,6,7,8,9],
        automation_assume_role_arn="test_role",
        execution_role_name="test_role",
        logger=get_logger(),
        regions=["us-east-1","us-east-2"],
        started_tags=[{'Key':'ScheduleStarted', 'Value': "Date-time-message"}],
        stopped_tags=[{'Key':'ScheduleStopped', 'Value': "Date-time-message"}]
    )
    get_mock = mocker.patch.object(handler, 'execute_ssm_api')
    handler.execute_ssm_api.return_value = 'aaas'
    response = handler.run_ssm_runbook(
        ssm_runbook_name="EC2_START_SSM_DOC",
        schedule_tag_name='Schedule',
        schedule_tag_value='office-hours-uk',
        tags=[{'Key':'ScheduleStarted', 'Value': "Date-time-message"}]
    )

    assert response == 'aaas'
    assert get_mock.call_count == 1
    calls = [
        call(ssm_runbook_name='EC2_START_SSM_DOC', schedule_tag_name='Schedule', schedule_tag_value='office-hours-uk', 
            tags=[{'Key':'ScheduleStarted', 'Value': "Date-time-message"}], 
            target_locations=[
                {'Accounts': [0, 1, 2, 3, 4], 'Regions': ['us-east-1', 'us-east-2'], 'ExecutionRoleName': 'test_role', 'TargetLocationMaxConcurrency': '100%', 'TargetLocationMaxErrors': '10%'}, 
                {'Accounts': [5, 6, 7, 8, 9], 'Regions': ['us-east-1', 'us-east-2'], 'ExecutionRoleName': 'test_role', 'TargetLocationMaxConcurrency': '100%', 'TargetLocationMaxErrors': '10%'}
            ])
        ]
    get_mock.assert_has_calls(calls)

def test_run_ssm_runbook_with_max_accounts(mocker):
    handler = SSMHandler(
        accounts=[0,1,2,3,4],
        automation_assume_role_arn="test_role",
        execution_role_name="test_role",
        logger=get_logger(),
        regions=["us-east-1","us-east-2"],
        started_tags=[{'Key':'ScheduleStarted', 'Value': "Date-time-message"}],
        stopped_tags=[{'Key':'ScheduleStopped', 'Value': "Date-time-message"}]
    )
    get_mock = mocker.patch.object(handler, 'execute_ssm_api')
    handler.execute_ssm_api.return_value = 'aaas'
    response = handler.run_ssm_runbook(
        ssm_runbook_name="EC2_START_SSM_DOC",
        schedule_tag_name='Schedule',
        schedule_tag_value='office-hours-uk',
        tags=[{'Key':'ScheduleStarted', 'Value': "Date-time-message"}]
    )

    assert response == 'aaas'
    assert get_mock.call_count == 1
    calls = [
        call(ssm_runbook_name='EC2_START_SSM_DOC', schedule_tag_name='Schedule', schedule_tag_value='office-hours-uk', 
            tags=[{'Key':'ScheduleStarted', 'Value': "Date-time-message"}], 
            target_locations=[{'Accounts': [0, 1, 2, 3, 4], 'Regions': ['us-east-1', 'us-east-2'], 'ExecutionRoleName': 'test_role', 'TargetLocationMaxConcurrency': '100%', 'TargetLocationMaxErrors': '10%'}])
        ]
    get_mock.assert_has_calls(calls)

def test_run_ssm_runbook_with_multiple_and_less_than_remainder_0_of_max_accounts(mocker):
    handler = SSMHandler(
        accounts=[0,1,2,3,4,5,6],
        automation_assume_role_arn="test_role",
        execution_role_name="test_role",
        logger=get_logger(),
        regions=["us-east-1","us-east-2"],
        started_tags=[{'Key':'ScheduleStarted', 'Value': "Date-time-message"}],
        stopped_tags=[{'Key':'ScheduleStopped', 'Value': "Date-time-message"}]
    )
    get_mock = mocker.patch.object(handler, 'execute_ssm_api')
    handler.execute_ssm_api.return_value = 'aaas'
    response = handler.run_ssm_runbook(
        ssm_runbook_name="EC2_START_SSM_DOC",
        schedule_tag_name='Schedule',
        schedule_tag_value='office-hours-uk',
        tags=[{'Key':'ScheduleStarted', 'Value': "Date-time-message"}],
    )
    assert response == 'aaas'
    assert get_mock.call_count == 1
    calls = [
        call(ssm_runbook_name='EC2_START_SSM_DOC', schedule_tag_name='Schedule', schedule_tag_value='office-hours-uk', 
        tags=[{'Key':'ScheduleStarted', 'Value': "Date-time-message"}], 
        target_locations=[
            {'Accounts': [0, 1, 2, 3, 4], 'Regions': ['us-east-1', 'us-east-2'], 'ExecutionRoleName': 'test_role', 'TargetLocationMaxConcurrency': '100%', 'TargetLocationMaxErrors': '10%'}, 
            {'Accounts': [5, 6], 'Regions': ['us-east-1', 'us-east-2'], 'ExecutionRoleName': 'test_role', 'TargetLocationMaxConcurrency': '100%', 'TargetLocationMaxErrors': '10%'}])
        ]
    get_mock.assert_has_calls(calls)

def test_start_run_rds_instances_document(mocker):
    handler = SSMHandler(
        accounts=[0,1,2,3,4,5,6],
        automation_assume_role_arn="test_role",
        execution_role_name="test_role",
        logger=get_logger(),
        regions=["us-east-1","us-east-2"],
        started_tags=[{'Key':'ScheduleStarted', 'Value': "Date-time-message"}],
        stopped_tags=[{'Key':'ScheduleStopped', 'Value': "Date-time-message"}]
    )
    get_mock = mocker.patch.object(handler, 'run_ssm_runbook')
    handler.run_ssm_runbook.return_value = 'aaas'

    response = handler.run_rds_instances_document('Schedule', 'office-hours-uk', 'running')

    assert get_mock.call_count == 1
    calls = [
        call('RDS_INSTANCES_START_SSM_DOC', 'Schedule', 'office-hours-uk', [{'Key':'ScheduleStarted', 'Value': "Date-time-message"}]) 
        ]
    get_mock.assert_has_calls(calls)
    assert response == 'aaas'
def test_stop_run_rds_instances_document(mocker):
    handler = SSMHandler(
        accounts=[0,1,2,3,4,5,6],
        automation_assume_role_arn="test_role",
        execution_role_name="test_role",
        logger=get_logger(),
        regions=["us-east-1","us-east-2"],
        started_tags=[{'Key':'ScheduleStarted', 'Value': "Date-time-message"}],
        stopped_tags=[{'Key':'ScheduleStopped', 'Value': "Date-time-message"}]
    )
    get_mock = mocker.patch.object(handler, 'run_ssm_runbook')
    handler.run_ssm_runbook.return_value = 'aaas'

    response = handler.run_rds_instances_document('Schedule', 'office-hours-uk', 'stopped')

    assert get_mock.call_count == 1
    calls = [
        call('RDS_INSTANCES_STOP_SSM_DOC', 'Schedule', 'office-hours-uk', [{'Key':'ScheduleStopped', 'Value': "Date-time-message"}]) 
        ]
    get_mock.assert_has_calls(calls)
    assert response == 'aaas'

def test_stop_run_rds_clusters_document(mocker):
    handler = SSMHandler(
        accounts=[0,1,2,3,4,5,6],
        automation_assume_role_arn="test_role",
        execution_role_name="test_role",
        logger=get_logger(),
        regions=["us-east-1","us-east-2"],
        started_tags=[{'Key':'ScheduleStarted', 'Value': "Date-time-message"}],
        stopped_tags=[{'Key':'ScheduleStopped', 'Value': "Date-time-message"}]
    )
    get_mock = mocker.patch.object(handler, 'run_ssm_runbook')
    handler.run_ssm_runbook.return_value = 'aaas'

    response = handler.run_rds_clusters_document('Schedule', 'office-hours-uk', 'stopped')

    assert get_mock.call_count == 1
    calls = [
        call('RDS_CLUSTERS_STOP_SSM_DOC', 'Schedule', 'office-hours-uk', [{'Key':'ScheduleStopped', 'Value': "Date-time-message"}]) 
        ]
    get_mock.assert_has_calls(calls)
    assert response == 'aaas'

def test_start_run_rds_clusters_document(mocker):
    handler = SSMHandler(
        accounts=[0,1,2,3,4,5,6],
        automation_assume_role_arn="test_role",
        execution_role_name="test_role",
        logger=get_logger(),
        regions=["us-east-1","us-east-2"],
        started_tags=[{'Key':'ScheduleStarted', 'Value': "Date-time-message"}],
        stopped_tags=[{'Key':'ScheduleStopped', 'Value': "Date-time-message"}]
    )
    get_mock = mocker.patch.object(handler, 'run_ssm_runbook')
    handler.run_ssm_runbook.return_value = 'aaas'

    response = handler.run_rds_clusters_document('Schedule', 'office-hours-uk', 'running')

    assert get_mock.call_count == 1
    calls = [
        call('RDS_CLUSTERS_START_SSM_DOC', 'Schedule', 'office-hours-uk', [{'Key':'ScheduleStarted', 'Value': "Date-time-message"}]) 
        ]
    get_mock.assert_has_calls(calls)
    assert response == 'aaas'
def test_start_run_ec2_document(mocker):
    handler = SSMHandler(
        accounts=[0,1,2,3,4,5,6],
        automation_assume_role_arn="test_role",
        execution_role_name="test_role",
        logger=get_logger(),
        regions=["us-east-1","us-east-2"],
        started_tags=[{'Key':'ScheduleStarted', 'Value': "Date-time-message"}],
        stopped_tags=[{'Key':'ScheduleStopped', 'Value': "Date-time-message"}]
    )
    get_mock = mocker.patch.object(handler, 'run_ssm_runbook')
    handler.run_ssm_runbook.return_value = 'aaas'

    response = handler.run_ec2_instances_document('Schedule', 'office-hours-uk', 'running')

    assert get_mock.call_count == 1
    calls = [
        call('EC2_START_SSM_DOC', 'Schedule', 'office-hours-uk', [{'Key':'ScheduleStarted', 'Value': "Date-time-message"}]) 
        ]
    get_mock.assert_has_calls(calls)
    assert response == 'aaas'
def test_stop_run_ec2_document(mocker):
    handler = SSMHandler(
        accounts=[0,1,2,3,4,5,6],
        automation_assume_role_arn="test_role",
        execution_role_name="test_role",
        logger=get_logger(),
        regions=["us-east-1","us-east-2"],
        started_tags=[{'Key':'ScheduleStarted', 'Value': "Date-time-message"}],
        stopped_tags=[{'Key':'ScheduleStopped', 'Value': "Date-time-message"}]
    )
    get_mock = mocker.patch.object(handler, 'run_ssm_runbook')
    handler.run_ssm_runbook.return_value = 'aaas'

    response = handler.run_ec2_instances_document('Schedule', 'office-hours-uk', 'stopped')

    assert get_mock.call_count == 1
    calls = [
        call('EC2_STOP_SSM_DOC', 'Schedule', 'office-hours-uk', [{'Key':'ScheduleStopped', 'Value': "Date-time-message"}])  
        ]
    get_mock.assert_has_calls(calls)
    assert response == 'aaas'


def test_get_tags_in_json_formatted_string_for_rds(): 
    handler = SSMHandler(
        accounts=[0,1,2,3,4,5,6],
        automation_assume_role_arn="test_role",
        execution_role_name="test_role",
        logger=get_logger(),
        regions=["us-east-1","us-east-2"],
        started_tags=[{'Key':'ScheduleStarted', 'Value': "Date-time-message"}],
        stopped_tags=[{'Key':'ScheduleStopped', 'Value': "Date-time-message"}]
    )
    response = handler.get_tags_in_json_formatted_string('RDS_CLUSTERS_START_SSM_DOC', [{'Key':'ScheduleStarted', 'Value': "Date-time-message"}])
    assert len(response) == 1
    assert response[0] == '{"ScheduleStarted": "Date-time-message"}'
def test_get_tags_in_json_formatted_string_for_rds_empty(): 
    handler = SSMHandler(
        accounts=[0,1,2,3,4,5,6],
        automation_assume_role_arn="test_role",
        execution_role_name="test_role",
        logger=get_logger(),
        regions=["us-east-1","us-east-2"],
        started_tags=[{'Key':'ScheduleStarted', 'Value': "Date-time-message"}],
        stopped_tags=[{'Key':'ScheduleStopped', 'Value': "Date-time-message"}]
    )
    response = handler.get_tags_in_json_formatted_string('RDS_CLUSTERS_START_SSM_DOC', [])
    assert len(response) == 1
    assert response[0] == '{"StateChanged": "Resource started by Instance Scheduler"}'
def test_get_tags_in_json_formatted_string_for_ec2(): 
    handler = SSMHandler(
        accounts=[0,1,2,3,4,5,6],
        automation_assume_role_arn="test_role",
        execution_role_name="test_role",
        logger=get_logger(),
        regions=["us-east-1","us-east-2"],
        started_tags=[{'Key':'ScheduleStarted', 'Value': "Date-time-message"}],
        stopped_tags=[{'Key':'ScheduleStopped', 'Value': "Date-time-message"}]
    )
    response = handler.get_tags_in_json_formatted_string('EC2_STOP_SSM_DOC', [{'Key':'ScheduleStarted', 'Value': "Date-time-message"}])
    assert len(response) == 1
    assert response[0] == '{"Key": "ScheduleStarted", "Value": "Date-time-message"}'
def test_get_tags_in_json_formatted_string_for_ec2_empty(): 
    handler = SSMHandler(
        accounts=[0,1,2,3,4,5,6],
        automation_assume_role_arn="test_role",
        execution_role_name="test_role",
        logger=get_logger(),
        regions=["us-east-1","us-east-2"],
        started_tags=[{'Key':'ScheduleStarted', 'Value': "Date-time-message"}],
        stopped_tags=[{'Key':'ScheduleStopped', 'Value': "Date-time-message"}]
    )
    response = handler.get_tags_in_json_formatted_string('EC2_STOP_SSM_DOC', [])
    assert len(response) == 1
    assert response[0] == '{"Key": "StateChanged", "Value": "Resource started by Instance Scheduler"}'

