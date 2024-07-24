# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from collections.abc import Iterator
from os import environ
from typing import TYPE_CHECKING, Final, Optional
from unittest.mock import patch

import boto3
from moto import mock_aws
from pytest import fixture

from instance_scheduler.model import EC2SSMMaintenanceWindowStore, MWStore
from instance_scheduler.model.ddb_config_item import DdbConfigItem
from instance_scheduler.model.store.ddb_config_item_store import DdbConfigItemStore
from instance_scheduler.model.store.dynamo_mw_store import DynamoMWStore
from instance_scheduler.model.store.dynamo_period_definition_store import (
    DynamoPeriodDefinitionStore,
)
from instance_scheduler.model.store.dynamo_schedule_definition_store import (
    DynamoScheduleDefinitionStore,
)
from instance_scheduler.model.store.period_definition_store import PeriodDefinitionStore
from instance_scheduler.model.store.schedule_definition_store import (
    ScheduleDefinitionStore,
)
from instance_scheduler.ops_metrics.metrics import MetricsEnvironment
from instance_scheduler.util.session_manager import AssumedRole
from tests import DEFAULT_REGION
from tests.test_utils.mock_metrics_environment import MockMetricsEnviron
from tests.test_utils.testsuite_env import TestSuiteEnv

if TYPE_CHECKING:
    from mypy_boto3_dynamodb.client import DynamoDBClient
    from mypy_boto3_ec2.client import EC2Client
    from mypy_boto3_ec2.type_defs import FilterTypeDef
    from mypy_boto3_logs.client import CloudWatchLogsClient
    from mypy_boto3_sns.client import SNSClient
else:
    DynamoDBClient = object
    EC2Client = object
    CloudWatchLogsClient = object
    SNSClient = object


@fixture(autouse=True)
def aws_credentials() -> Iterator[None]:
    creds = {
        "AWS_ACCESS_KEY_ID": "testing",
        "AWS_SECRET_ACCESS_KEY": "testing",
        "AWS_SECURITY_TOKEN": "testing",
        "AWS_SESSION_TOKEN": "testing",
        "AWS_DEFAULT_REGION": DEFAULT_REGION,
    }
    with patch.dict(environ, creds, clear=True):
        yield


@fixture(autouse=True)
def test_suite_env(aws_credentials: None) -> Iterator[TestSuiteEnv]:
    with TestSuiteEnv() as env:
        yield env


@fixture(autouse=True)
def metrics_environment() -> Iterator[MetricsEnvironment]:
    with MockMetricsEnviron() as metrics_env:
        yield metrics_env


@fixture
def moto_backend() -> Iterator[None]:
    with mock_aws():
        yield


def get_ami(region: str = "us-east-1") -> str:
    ec2: Final[EC2Client] = boto3.client("ec2", region_name=region)
    paginator: Final = ec2.get_paginator("describe_images")
    filters: Final[list[FilterTypeDef]] = [
        {"Name": "name", "Values": ["al2023-ami-minimal-*-arm64"]},
    ]
    image_id: Optional[str] = None
    for page in paginator.paginate(Filters=filters, Owners=["amazon"]):
        if page["Images"]:
            image_id = page["Images"][0]["ImageId"]
            break
    if not image_id:
        raise ValueError("No AMI found")
    return image_id


@fixture()
def hub_role() -> AssumedRole:
    return AssumedRole(
        role_name="hub-role",
        account="123456789012",
        region="us-east-1",
        session=boto3.Session(),
    )


@fixture
def ami(moto_backend: None) -> Iterator[str]:
    yield get_ami()


@fixture
def dynamodb_client(moto_backend: None) -> Iterator[DynamoDBClient]:
    """DDB Mock Client"""
    connection = boto3.client("dynamodb", region_name="us-east-1")
    yield connection


@fixture
def config_item_store(
    config_table: str,
) -> DdbConfigItemStore:
    store = DdbConfigItemStore(config_table)
    store.put(
        DdbConfigItem("", [])
    )  # expected to always exist as these are set up by the initial custom resource
    return store


@fixture
def schedule_store(config_table: str) -> ScheduleDefinitionStore:
    return DynamoScheduleDefinitionStore(config_table)


@fixture
def period_store(config_table: str) -> PeriodDefinitionStore:
    return DynamoPeriodDefinitionStore(config_table)


@fixture
def config_table(test_suite_env: TestSuiteEnv, moto_backend: None) -> Iterator[str]:
    boto3.client("dynamodb").create_table(
        AttributeDefinitions=[
            {"AttributeName": "name", "AttributeType": "S"},
            {"AttributeName": "type", "AttributeType": "S"},
        ],
        TableName=test_suite_env.config_table_name,
        KeySchema=[
            {"AttributeName": "type", "KeyType": "HASH"},
            {"AttributeName": "name", "KeyType": "RANGE"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )
    yield test_suite_env.config_table_name


@fixture
def maint_win_table(test_suite_env: TestSuiteEnv, moto_backend: None) -> Iterator[str]:
    table_name: Final = test_suite_env.maintenance_window_table_name
    ddb: Final[DynamoDBClient] = boto3.client("dynamodb")
    ddb.create_table(
        AttributeDefinitions=[
            {"AttributeName": "account-region", "AttributeType": "S"},
            {"AttributeName": "name-id", "AttributeType": "S"},
        ],
        TableName=table_name,
        KeySchema=[
            {"AttributeName": "account-region", "KeyType": "HASH"},
            {"AttributeName": "name-id", "KeyType": "RANGE"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )
    yield table_name


@fixture()
def maint_win_store(maint_win_table: str) -> EC2SSMMaintenanceWindowStore:
    return EC2SSMMaintenanceWindowStore(maint_win_table)


@fixture()
def mw_store(maint_win_table: str) -> MWStore:
    return DynamoMWStore(maint_win_table)


@fixture
def mock_log_group(moto_backend: None, test_suite_env: TestSuiteEnv) -> None:
    logs: CloudWatchLogsClient = boto3.client("logs")
    logs.create_log_group(logGroupName=test_suite_env.log_group)


@fixture
def mock_sns_errors_topic(moto_backend: None, test_suite_env: TestSuiteEnv) -> None:
    sns: SNSClient = boto3.client("sns")
    sns.create_topic(Name=test_suite_env.topic_arn.split(":")[-1])
