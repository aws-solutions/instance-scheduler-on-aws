# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from collections.abc import Iterator
from typing import TYPE_CHECKING

import boto3
from instance_scheduler.scheduling.asg.asg_runtime_info import AsgRuntimeInfo
from instance_scheduler.scheduling.asg.asg_size import AsgSize
from instance_scheduler.scheduling.resource_registration import register_asg_resources
from instance_scheduler.util.session_manager import lambda_execution_role
from pytest import fixture
from tests.integration.helpers.asg_helpers import create_asg
from tests.test_utils.mock_resource_registration_environment import (
    MockResourceRegistrationEnvironment,
)
from tests.test_utils.testsuite_env import MockSuiteEnv

if TYPE_CHECKING:
    from mypy_boto3_dynamodb import DynamoDBClient
    from mypy_boto3_ec2.client import EC2Client
    from mypy_boto3_rds.client import RDSClient
    from mypy_boto3_rds.type_defs import CreateDBInstanceResultTypeDef
else:
    DynamoDBClient = object
    EC2Client = object
    RDSClient = object
    CreateDBInstanceResultTypeDef = object


@fixture(autouse=True)
def auto_setup_sns_error_reporting_topic(mock_sns_errors_topic: None) -> None:
    """noop"""


@fixture
def ec2_instance(moto_backend: None, ami: str) -> Iterator[str]:
    ec2_client: EC2Client = boto3.client("ec2")
    instance_id: str = ec2_client.run_instances(ImageId=ami, MinCount=1, MaxCount=1)[
        "Instances"
    ][0]["InstanceId"]
    ec2_client.create_tags(
        Resources=[instance_id], Tags=[{"Key": "Schedule", "Value": "test-schedule"}]
    )
    yield instance_id


@fixture
def asg(registry_table: str) -> Iterator[AsgRuntimeInfo]:
    asg_def = create_asg("test-asg", AsgSize(1, 3, 5), "test-schedule")
    register_asg_resources(
        [asg_def], lambda_execution_role(), MockResourceRegistrationEnvironment()
    )
    yield asg_def


@fixture
def rds_instance(moto_backend: None) -> Iterator[str]:
    instance_id = "rds-test-instance"
    rds_client: RDSClient = boto3.client("rds")
    result: CreateDBInstanceResultTypeDef = rds_client.create_db_instance(
        DBInstanceIdentifier=instance_id,
        DBInstanceClass="db.m5.large",
        Engine="postgres",
    )
    instance_arn = result["DBInstance"]["DBInstanceArn"]
    rds_client.add_tags_to_resource(
        ResourceName=instance_arn, Tags=[{"Key": "Schedule", "Value": "test-schedule"}]
    )
    yield instance_id


@fixture
def rds_cluster(moto_backend: None) -> Iterator[str]:
    cluster_id = "rds-test-cluster"
    engine = "aurora-mysql"
    rds: RDSClient = boto3.client("rds")
    result = rds.create_db_cluster(
        DBClusterIdentifier=cluster_id,
        Engine=engine,
        MasterUsername="admin",
        MasterUserPassword="password",
    )
    arn = result["DBCluster"]["DBClusterArn"]
    rds.add_tags_to_resource(
        ResourceName=arn, Tags=[{"Key": "Schedule", "Value": "test-schedule"}]
    )
    rds.create_db_instance(
        DBInstanceIdentifier="rds-test-instance",
        DBClusterIdentifier=cluster_id,
        Engine=engine,
        DBInstanceClass="db.m5.large",
    )
    yield cluster_id


@fixture
def state_table(moto_backend: None, test_suite_env: MockSuiteEnv) -> str:
    state_table_name = test_suite_env.state_table_name
    dynamo_client: DynamoDBClient = boto3.client("dynamodb")
    dynamo_client.create_table(
        TableName=state_table_name,
        AttributeDefinitions=[
            {"AttributeName": "service", "AttributeType": "S"},
            {"AttributeName": "account-region", "AttributeType": "S"},
        ],
        KeySchema=[
            {"AttributeName": "service", "KeyType": "HASH"},
            {"AttributeName": "account-region", "KeyType": "RANGE"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )
    return state_table_name
