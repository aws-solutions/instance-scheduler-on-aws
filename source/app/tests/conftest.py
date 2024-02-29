# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from collections.abc import Iterator
from os import environ
from typing import TYPE_CHECKING, Final
from unittest.mock import patch

import boto3
from moto import mock_aws
from pytest import fixture

import instance_scheduler.util.app_env
from instance_scheduler.configuration import unload_global_configuration
from instance_scheduler.util.app_env import AppEnv
from tests.util.test_app_env import env_from_app_env, example_app_env

if TYPE_CHECKING:
    from mypy_boto3_dynamodb.client import DynamoDBClient
    from mypy_boto3_logs.client import CloudWatchLogsClient
    from mypy_boto3_sns.client import SNSClient
else:
    DynamoDBClient = object
    CloudWatchLogsClient = object
    SNSClient = object


@fixture(autouse=True)
def aws_credentials() -> Iterator[None]:
    creds = {
        "AWS_ACCESS_KEY_ID": "testing",
        "AWS_SECRET_ACCESS_KEY": "testing",
        "AWS_SECURITY_TOKEN": "testing",
        "AWS_SESSION_TOKEN": "testing",
        "AWS_DEFAULT_REGION": "us-east-1",
    }
    with patch.dict(environ, creds, clear=True):
        yield


@fixture(autouse=True)
def app_env(aws_credentials: None) -> Iterator[AppEnv]:
    # clear cached env for each test for isolation
    instance_scheduler.util.app_env._app_env = None
    env = example_app_env()
    with patch.dict(environ, env_from_app_env(env)):
        yield env


@fixture(autouse=True)
def test_cleanup() -> Iterator[None]:
    # runs before each test
    yield
    # runs after each test
    unload_global_configuration()


@fixture
def moto_backend() -> Iterator[None]:
    with mock_aws():
        yield


@fixture
def dynamodb_client(moto_backend: None) -> Iterator[DynamoDBClient]:
    """DDB Mock Client"""
    connection = boto3.client("dynamodb", region_name="us-east-1")
    yield connection


@fixture
def config_table(app_env: AppEnv, moto_backend: None) -> None:
    boto3.client("dynamodb").create_table(
        AttributeDefinitions=[
            {"AttributeName": "name", "AttributeType": "S"},
            {"AttributeName": "type", "AttributeType": "S"},
        ],
        TableName=app_env.config_table_name,
        KeySchema=[
            {"AttributeName": "type", "KeyType": "HASH"},
            {"AttributeName": "name", "KeyType": "RANGE"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )


@fixture
def maint_win_table(moto_backend: None, app_env: AppEnv) -> str:
    maint_win_table_name: Final = app_env.maintenance_window_table_name
    ddb: Final[DynamoDBClient] = boto3.client("dynamodb")
    ddb.create_table(
        AttributeDefinitions=[
            {"AttributeName": "Name", "AttributeType": "S"},
            {"AttributeName": "account-region", "AttributeType": "S"},
        ],
        TableName=maint_win_table_name,
        KeySchema=[
            {"AttributeName": "Name", "KeyType": "HASH"},
            {"AttributeName": "account-region", "KeyType": "RANGE"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )
    return maint_win_table_name


@fixture
def mock_log_group(moto_backend: None, app_env: AppEnv) -> None:
    logs: CloudWatchLogsClient = boto3.client("logs")
    logs.create_log_group(logGroupName=app_env.log_group)


@fixture
def mock_sns_errors_topic(moto_backend: None, app_env: AppEnv) -> None:
    sns: SNSClient = boto3.client("sns")
    sns.create_topic(Name=app_env.topic_arn.split(":")[-1])
