# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0


import os
import pytest

TABLE_NAME = "mock-schedule-state-table"
CONFIG_TABLE_NAME = "mock-schedule-state-table"


@pytest.hookimpl(tryfirst=True)
def pytest_load_initial_conftests():
    os.environ["SCHEDULE_STATES_TABLE"] = TABLE_NAME
    os.environ["CONFIG_TABLE"] = CONFIG_TABLE_NAME
    os.environ["LOG_GROUP"] = "instance-scheduler-logs"
    os.environ["ACCOUNT"] = "111111111111"
    os.environ["SSM_EXECUTION_ROLE_NAME"] = "role/role_name"
    os.environ["SSM_ADMIN_ROLE_NAME"] = "role/role_name"
    os.environ["RDS_INSTANCES_START_SSM_DOC"] = "RDS_INSTANCES_START_SSM_DOC"
    os.environ["RDS_INSTANCES_STOP_SSM_DOC"] = "RDS_INSTANCES_STOP_SSM_DOC"
    os.environ["RDS_CLUSTERS_START_SSM_DOC"] = "RDS_CLUSTERS_START_SSM_DOC"
    os.environ["RDS_CLUSTERS_STOP_SSM_DOC"] = "RDS_CLUSTERS_STOP_SSM_DOC"
    os.environ["EC2_START_SSM_DOC"] = "EC2_START_SSM_DOC"
    os.environ["EC2_STOP_SSM_DOC"] = "EC2_STOP_SSM_DOC"
    os.environ["TRACE"] = "DEBUG"
    os.environ["aws_partition"] = "aws"
    os.environ["namespace"] = "test"
    os.environ["AWS_REGION"] = "us-east-1"
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
    os.environ["SOLUTION_ID"] = "SOTestID"
    os.environ["AWS_ACCOUNT"] = "123456789012"
