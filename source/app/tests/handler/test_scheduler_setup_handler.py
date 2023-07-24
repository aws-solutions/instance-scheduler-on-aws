# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from os import environ

import boto3

from instance_scheduler.handler.config_resource import SchedulerSetupHandler
from instance_scheduler.util.app_env import AppEnv
from tests.context import MockLambdaContext


def test_a_valid_org_id_pattern() -> None:
    handler = SchedulerSetupHandler(
        {"ResourceProperties": {"stack_version": "test"}}, MockLambdaContext()
    )
    response = handler.get_valid_org_id("o-x1mhq1lvsr")
    assert response


def test_an_invalid_org_id_pattern() -> None:
    handler = SchedulerSetupHandler(
        {"ResourceProperties": {"stack_version": "test"}}, MockLambdaContext()
    )
    response = handler.get_valid_org_id("111111111111,222222222222")
    assert response is None


def test_create_request(config_table: None) -> None:
    """Happy path no errors"""
    handler = SchedulerSetupHandler(
        {
            "ResourceProperties": {
                "stack_version": "test",
                "remote_account_ids": ["111111111111"],
                "scheduled_services": ["ec2"],
                "regions": ["us-east-1"],
            }
        },
        MockLambdaContext(),
    )
    assert handler._create_request() is True


def test_update_request(config_table: None) -> None:
    """Happy path no errors"""
    handler = SchedulerSetupHandler(
        {
            "ResourceProperties": {
                "stack_version": "test",
                "remote_account_ids": ["111111111111"],
                "scheduled_services": ["ec2"],
                "regions": ["us-east-1"],
            }
        },
        MockLambdaContext(),
    )
    assert handler._update_request() is True


def test_regions() -> None:
    regions = ["us-east-1", "us-west-2"]
    handler = SchedulerSetupHandler(
        {"ResourceProperties": {"stack_version": "test", "regions": regions}},
        MockLambdaContext(),
    )
    assert handler.regions == set(regions)


def test_regions_empty() -> None:
    handler = SchedulerSetupHandler(
        {"ResourceProperties": {"stack_version": "test", "regions": []}},
        MockLambdaContext(),
    )
    assert handler.regions == [environ["AWS_DEFAULT_REGION"]]


def test_regions_empty_strings() -> None:
    handler = SchedulerSetupHandler(
        {"ResourceProperties": {"stack_version": "test", "regions": ["", ""]}},
        MockLambdaContext(),
    )
    assert handler.regions == [environ["AWS_DEFAULT_REGION"]]


def test_remote_account_ids() -> None:
    accounts = ["111111111111", "222222222222"]
    handler = SchedulerSetupHandler(
        {
            "ResourceProperties": {
                "stack_version": "test",
                "remote_account_ids": accounts,
            }
        },
        MockLambdaContext(),
    )
    assert handler.remote_account_ids == set(accounts)


def test_remote_account_ids_empty() -> None:
    handler = SchedulerSetupHandler(
        {"ResourceProperties": {"stack_version": "test", "remote_account_ids": []}},
        MockLambdaContext(),
    )
    assert not handler.remote_account_ids


def test_remote_account_ids_empty_strings() -> None:
    handler = SchedulerSetupHandler(
        {
            "ResourceProperties": {
                "stack_version": "test",
                "remote_account_ids": ["", ""],
            }
        },
        MockLambdaContext(),
    )
    assert not handler.remote_account_ids


def test_scheduled_services() -> None:
    services = ["ec2", "rds"]
    handler = SchedulerSetupHandler(
        {
            "ResourceProperties": {
                "stack_version": "test",
                "scheduled_services": services,
            }
        },
        MockLambdaContext(),
    )
    assert handler.scheduled_services == set(services)


def test_scheduled_services_empty() -> None:
    handler = SchedulerSetupHandler(
        {"ResourceProperties": {"stack_version": "test", "scheduled_services": []}},
        MockLambdaContext(),
    )
    assert not handler.scheduled_services


def test_scheduled_services_empty_strings() -> None:
    handler = SchedulerSetupHandler(
        {
            "ResourceProperties": {
                "stack_version": "test",
                "scheduled_services": ["", ""],
            }
        },
        MockLambdaContext(),
    )
    assert not handler.scheduled_services


def test_set_lambda_logs_retention_period(app_env: AppEnv) -> None:
    """With no period, expect set to default"""
    log_group = app_env.log_group
    handler = SchedulerSetupHandler(
        {"ResourceProperties": {"stack_version": "test"}}, MockLambdaContext(log_group)
    )
    handler.set_lambda_logs_retention_period()
    response = boto3.client("logs").describe_log_groups(logGroupNamePrefix=log_group)
    assert response["logGroups"][0]["logGroupName"] == log_group
    assert response["logGroups"][0]["retentionInDays"] == 30


def test_set_lambda_logs_retention_period_custom_retention(app_env: AppEnv) -> None:
    """With custom period, expect set to desired"""
    log_group = app_env.log_group
    retention_period = 90
    handler = SchedulerSetupHandler(
        {
            "ResourceProperties": {
                "stack_version": "test",
                "log_retention_days": retention_period,
            }
        },
        MockLambdaContext(log_group),
    )
    handler.set_lambda_logs_retention_period()
    response = boto3.client("logs").describe_log_groups(logGroupNamePrefix=log_group)
    assert response["logGroups"][0]["logGroupName"] == log_group
    assert response["logGroups"][0]["retentionInDays"] == retention_period
