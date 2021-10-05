######################################################################################################################
#  Copyright 2021 Amazon.com, Inc. or its affiliates. All Rights Reserved.                                           #
#                                                                                                                    #
#  Licensed under the Apache License Version 2.0 [the "License"] = . You may not use this file except in compliance     #
#  with the License. A copy of the License is located at                                                             #
#                                                                                                                    #
#      http://www.apache.org/licenses/                                                                               #
#                                                                                                                    #
#  or in the "license" file accompanying this file. This file is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES #
#  OR CONDITIONS OF ANY KIND, express or implied. See the License for the specific language governing permissions    #
#  and limitations under the License.                                                                                #
######################################################################################################################


import os
import pytest

TABLE_NAME = 'mock-schedule-state-table'
CONFIG_TABLE_NAME = 'mock-schedule-state-table'

@pytest.hookimpl(tryfirst=True)
def pytest_load_initial_conftests():
    os.environ['SCHEDULE_STATES_TABLE'] = TABLE_NAME
    os.environ['CONFIG_TABLE'] = CONFIG_TABLE_NAME
    os.environ['LOG_GROUP'] = 'instance-scheduler-logs'
    os.environ['ACCOUNT'] = '111111111111'
    os.environ['SSM_EXECUTION_ROLE_NAME'] = 'role/role_name'
    os.environ['SSM_ADMIN_ROLE_NAME'] = 'role/role_name'
    os.environ['RDS_INSTANCES_START_SSM_DOC'] = 'RDS_INSTANCES_START_SSM_DOC'
    os.environ['RDS_INSTANCES_STOP_SSM_DOC'] = 'RDS_INSTANCES_STOP_SSM_DOC'
    os.environ['RDS_CLUSTERS_START_SSM_DOC'] = 'RDS_CLUSTERS_START_SSM_DOC'
    os.environ['RDS_CLUSTERS_STOP_SSM_DOC'] = 'RDS_CLUSTERS_STOP_SSM_DOC'
    os.environ['EC2_START_SSM_DOC'] = 'EC2_START_SSM_DOC'
    os.environ['EC2_STOP_SSM_DOC'] = 'EC2_STOP_SSM_DOC'
    os.environ["TRACE"] = 'DEBUG'
    os.environ['aws_partition'] = 'aws'
    os.environ['namespace'] = 'test'
    os.environ['execution_role_name'] = 'Scheduler-AutomationExecutionRole'
    os.environ['AWS_REGION'] = 'us-east-1'
    os.environ['MAX_ALLOWED_ACCOUNTS_IN_SSM_API'] = "5"
    os.environ["SSM_MAX_CONCURRENCY"] = "100%"
    os.environ["SSM_MAX_ERRORS"] = "10%"