# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

import json
from os import environ
from typing import Iterator, Mapping
from unittest.mock import MagicMock, patch

from _pytest.fixtures import fixture
from aws_lambda_powertools import Logger
from instance_scheduler.handler.environments.region_registration_environment import (
    RegionRegistrationEnvironment,
)
from instance_scheduler.handler.region_registration_events_handler import (
    RegionRegistrationHandler,
    RegionRegistrationProperties,
)
from instance_scheduler.util.custom_resource import CustomResourceRequest
from tests.context import MockLambdaContext


@fixture
def mocked_environment() -> Iterator[Mapping[str, str]]:
    mocked_environment = {
        "USER_AGENT_EXTRA": "test-agent",
        "HUB_ACCOUNT_ID": "123456789012",
        "HUB_REGISTRATION_ROLE_NAME": "test-role",
        "HUB_REGISTRATION_FUNCTION_ARN": "arn:aws:lambda:us-east-1:123456789012:function:test-function",
        "SSM_PARAM_PATH": "/instance-scheduler/regions",
        "STACK_ID": "arn:aws:cloudformation:us-west-2:111122223333:stack/test-stack/51af3dc0-da77-11e4-872e-1234567db123",
    }
    with patch.dict(environ, mocked_environment, clear=True):
        yield mocked_environment


@fixture
def custom_resource_base_event() -> CustomResourceRequest[RegionRegistrationProperties]:
    return {
        "RequestType": "Create",
        "ServiceToken": "LambdaARN",
        "ResponseURL": "url",
        "StackId": "arn:aws:cloudformation:us-west-2:111122223333:stack/teststack/51af3dc0-da77-11e4-872e-1234567db123",
        "RequestId": "requestId",
        "ResourceType": "Custom::RegionRegistration",
        "LogicalResourceId": "CFNLogicalID",
        "PhysicalResourceId": "PhysicalID",
        "ResourceProperties": {"regions": ["us-east-1", "us-west-2"]},
    }


@fixture
def mocked_clients() -> Iterator[tuple[MagicMock, MagicMock]]:
    mock_lambda_client = MagicMock()
    mock_ssm_service = MagicMock()

    with patch(
        "instance_scheduler.handler.region_registration_events_handler.lambda_execution_role"
    ) as mock_lambda_role, patch(
        "instance_scheduler.handler.region_registration_events_handler.assume_role"
    ) as mock_assume_role, patch(
        "instance_scheduler.handler.region_registration_events_handler.SSMService"
    ) as mock_ssm_class, patch(
        "instance_scheduler.handler.region_registration_events_handler.PoolManager"
    ) as mock_pool_manager:

        mock_assumed_role = MagicMock()
        mock_assumed_role.client.return_value = mock_lambda_client
        mock_assumed_role.region = "us-east-1"
        mock_assumed_role.account = "123456789012"
        mock_lambda_role.return_value = mock_assumed_role
        mock_assume_role.return_value = mock_assumed_role
        mock_ssm_class.return_value = mock_ssm_service

        # Mock HTTP response for CloudFormation callback
        mock_http = MagicMock()
        mock_pool_manager.return_value = mock_http
        mock_http.request.return_value = MagicMock(status=200)

        yield mock_lambda_client, mock_ssm_service


def test_create_request_success(
    mocked_clients: tuple[MagicMock, MagicMock],
    custom_resource_base_event: CustomResourceRequest[RegionRegistrationProperties],
    mocked_environment: Mapping[str, str],
) -> None:
    mock_lambda_client, mock_ssm_service = mocked_clients
    context = MockLambdaContext()
    logger = Logger()
    env = RegionRegistrationEnvironment.from_env()

    handler = RegionRegistrationHandler(
        custom_resource_base_event, context, logger, env
    )
    handler.handle_request()

    # Verify lambda invoke was called for both regions
    assert mock_lambda_client.invoke.call_count == 2

    # Verify SSM parameters were set for both regions
    assert mock_ssm_service.put_parameter.call_count == 2

    # Verify lambda invocation payloads
    calls = mock_lambda_client.invoke.call_args_list
    for call in calls:
        payload = json.loads(call.kwargs["Payload"].decode())
        assert payload["account"] == "123456789012"
        assert payload["operation"] == "Register"
        assert payload["region"] in ["us-east-1", "us-west-2"]
        assert (
            call.kwargs["FunctionName"]
            == "arn:aws:lambda:us-east-1:123456789012:function:test-function"
        )
        assert call.kwargs["InvocationType"] == "Event"

    # Verify SSM parameter calls
    ssm_calls = mock_ssm_service.put_parameter.call_args_list
    for call in ssm_calls:
        assert call.kwargs["name"].startswith("/instance-scheduler/regions/")
        assert call.kwargs["value"] == "created"


def test_create_request_empty_regions_uses_default(
    mocked_clients: tuple[MagicMock, MagicMock],
    mocked_environment: Mapping[str, str],
) -> None:
    mock_lambda_client, mock_ssm_service = mocked_clients
    event = {
        "RequestType": "Create",
        "ResourceProperties": {"regions": []},
        "StackId": "arn:aws:cloudformation:us-west-2:111122223333:stack/test-stack/51af3dc0-da77-11e4-872e-1234567db123",
        "RequestId": "test-request",
        "LogicalResourceId": "test-logical-id",
        "ResponseURL": "test-url",
    }

    context = MockLambdaContext()
    logger = Logger()
    env = RegionRegistrationEnvironment.from_env()

    handler = RegionRegistrationHandler(event, context, logger, env)
    handler.handle_request()

    # Verify lambda invoke was called once for default region
    assert mock_lambda_client.invoke.call_count == 1

    call = mock_lambda_client.invoke.call_args
    payload = json.loads(call.kwargs["Payload"].decode())
    assert payload["region"] == "us-east-1"  # Default region from mock


def test_update_request_success(
    mocked_clients: tuple[MagicMock, MagicMock],
    mocked_environment: Mapping[str, str],
) -> None:
    mock_lambda_client, mock_ssm_service = mocked_clients
    event = {
        "RequestType": "Update",
        "ResourceProperties": {"regions": ["us-east-1", "us-west-2", "eu-west-1"]},
        "OldResourceProperties": {"regions": ["us-east-1", "ap-south-1"]},
        "StackId": "arn:aws:cloudformation:us-west-2:111122223333:stack/test-stack/51af3dc0-da77-11e4-872e-1234567db123",
        "RequestId": "test-request",
        "LogicalResourceId": "test-logical-id",
        "ResponseURL": "test-url",
    }

    context = MockLambdaContext()
    logger = Logger()
    env = RegionRegistrationEnvironment.from_env()

    handler = RegionRegistrationHandler(event, context, logger, env)
    handler.handle_request()

    # Verify lambda invoke was called for deregistration and registration
    assert mock_lambda_client.invoke.call_count == 3  # 1 deregister + 2 register

    calls = mock_lambda_client.invoke.call_args_list

    # Check deregistration event for ap-south-1
    deregister_payload = json.loads(calls[0].kwargs["Payload"].decode())
    assert deregister_payload["operation"] == "Deregister"
    assert deregister_payload["region"] == "ap-south-1"

    # Check registration events for new regions
    register_calls = calls[1:]
    register_regions = []
    for call in register_calls:
        payload = json.loads(call.kwargs["Payload"].decode())
        assert payload["operation"] == "Register"
        register_regions.append(payload["region"])

    assert set(register_regions) == {"us-west-2", "eu-west-1"}

    # Verify SSM parameters were set
    assert mock_ssm_service.put_parameter.call_count == 3
    ssm_calls = mock_ssm_service.put_parameter.call_args_list
    assert ssm_calls[0].kwargs["value"] == "deleting"  # For deregistration
    assert ssm_calls[1].kwargs["value"] == "created"  # For registration
    assert ssm_calls[2].kwargs["value"] == "created"  # For registration


def test_delete_request_success(
    mocked_clients: tuple[MagicMock, MagicMock],
    mocked_environment: Mapping[str, str],
) -> None:
    mock_lambda_client, mock_ssm_service = mocked_clients
    event = {
        "RequestType": "Delete",
        "ResourceProperties": {"regions": ["us-east-1", "us-west-2"]},
        "StackId": "arn:aws:cloudformation:us-west-2:111122223333:stack/test-stack/51af3dc0-da77-11e4-872e-1234567db123",
        "RequestId": "test-request",
        "LogicalResourceId": "test-logical-id",
        "ResponseURL": "test-url",
    }

    context = MockLambdaContext()
    logger = Logger()
    env = RegionRegistrationEnvironment.from_env()

    handler = RegionRegistrationHandler(event, context, logger, env)
    handler.handle_request()

    # Verify lambda invoke was called for both regions with deregister operation
    assert mock_lambda_client.invoke.call_count == 2

    calls = mock_lambda_client.invoke.call_args_list
    deregister_regions = []
    for call in calls:
        payload = json.loads(call.kwargs["Payload"].decode())
        assert payload["operation"] == "Deregister"
        assert payload["account"] == "123456789012"
        deregister_regions.append(payload["region"])

    assert set(deregister_regions) == {"us-east-1", "us-west-2"}

    # Verify SSM parameters were set
    assert mock_ssm_service.put_parameter.call_count == 2
    ssm_calls = mock_ssm_service.put_parameter.call_args_list
    for call in ssm_calls:
        assert call.kwargs["value"] == "deleting"


def test_update_request_empty_old_regions_uses_default(
    mocked_clients: tuple[MagicMock, MagicMock],
    mocked_environment: Mapping[str, str],
) -> None:
    mock_lambda_client, mock_ssm_service = mocked_clients
    event = {
        "RequestType": "Update",
        "ResourceProperties": {"regions": ["us-west-2"]},
        "OldResourceProperties": {"regions": []},
        "StackId": "arn:aws:cloudformation:us-west-2:111122223333:stack/test-stack/51af3dc0-da77-11e4-872e-1234567db123",
        "RequestId": "test-request",
        "LogicalResourceId": "test-logical-id",
        "ResponseURL": "test-url",
    }

    context = MockLambdaContext()
    logger = Logger()
    env = RegionRegistrationEnvironment.from_env()

    handler = RegionRegistrationHandler(event, context, logger, env)
    handler.handle_request()

    # When old_regions is empty, it defaults to ["us-east-1"]
    # current_regions is ["us-west-2"]
    # So we deregister "us-east-1" and register "us-west-2"
    assert mock_lambda_client.invoke.call_count == 2

    calls = mock_lambda_client.invoke.call_args_list

    # First call should be deregistration of us-east-1
    deregister_payload = json.loads(calls[0].kwargs["Payload"].decode())
    assert deregister_payload["operation"] == "Deregister"
    assert deregister_payload["region"] == "us-east-1"

    # Second call should be registration of us-west-2
    register_payload = json.loads(calls[1].kwargs["Payload"].decode())
    assert register_payload["operation"] == "Register"
    assert register_payload["region"] == "us-west-2"
