# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from collections.abc import Iterator
from typing import TYPE_CHECKING

import boto3
from moto import mock_rds, mock_resourcegroupstaggingapi
from pytest import fixture

from instance_scheduler.schedulers.instance_states import InstanceStates
from instance_scheduler.util.app_env import AppEnv
from tests import ami
from tests.logger import MockLogger

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
def moto_logs_autouse(moto_logs: None) -> Iterator[None]:
    yield


@fixture(autouse=True)
def mock_log_group_autouse(mock_log_group: None) -> None:
    """noop"""


@fixture(autouse=True)
def moto_sns_autouse(moto_sns: None) -> Iterator[None]:
    yield


@fixture(autouse=True)
def mock_topic_autouse(mock_topic: None) -> None:
    """noop"""


@fixture(autouse=True)
def moto_sts_autouse(moto_sts: None) -> Iterator[None]:
    yield


@fixture
def moto_rds() -> Iterator[None]:
    with mock_rds():
        yield


@fixture
def moto_resource_group_tagging_api() -> Iterator[None]:
    with mock_resourcegroupstaggingapi():
        yield


@fixture
def ec2_instance(moto_ec2: None) -> Iterator[str]:
    ec2_client: EC2Client = boto3.client("ec2")
    instance_id: str = ec2_client.run_instances(ImageId=ami, MinCount=1, MaxCount=1)[
        "Instances"
    ][0]["InstanceId"]
    ec2_client.create_tags(
        Resources=[instance_id], Tags=[{"Key": "Schedule", "Value": "test-schedule"}]
    )
    yield instance_id


@fixture
def rds_instance(
    moto_rds: None, moto_resource_group_tagging_api: None
) -> Iterator[str]:
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
def rds_cluster(moto_rds: None, moto_resource_group_tagging_api: None) -> Iterator[str]:
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
def state_table(moto_dynamodb: None, app_env: AppEnv) -> str:
    state_table_name = app_env.state_table_name
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


@fixture
def ec2_instance_states(state_table: str) -> InstanceStates:
    instance_states = InstanceStates(state_table, "ec2", MockLogger())
    instance_states.load(account="123456789012", region="us-east-1")
    return instance_states


@fixture
def rds_instance_states(state_table: str) -> InstanceStates:
    instance_states = InstanceStates(state_table, "rds", MockLogger())
    instance_states.load(account="123456789012", region="us-east-1")
    return instance_states
