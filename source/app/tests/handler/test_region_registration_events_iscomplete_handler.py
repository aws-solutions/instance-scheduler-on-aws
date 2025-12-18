# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

from os import environ
from typing import Iterator, Mapping
from unittest.mock import MagicMock, patch

from _pytest.fixtures import fixture
from aws_lambda_powertools import Logger
from instance_scheduler.handler.environments.region_registration_environment import (
    RegionRegistrationEnvironment,
)
from instance_scheduler.handler.region_registration_events_iscomplete_handler import (
    RegionRegistrationIsCompleteHandler,
    RegionRegistrationIsCompleteProperties,
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
        "SSM_PARAM_PATH": "/instance-scheduler/namespace/regions",
        "STACK_ID": "arn:aws:cloudformation:us-west-2:111122223333:stack/test-stack/51af3dc0-da77-11e4-872e-1234567db123",
    }
    with patch.dict(environ, mocked_environment, clear=True):
        yield mocked_environment


@fixture
def custom_resource_base_event() -> (
    CustomResourceRequest[RegionRegistrationIsCompleteProperties]
):
    return {
        "RequestType": "Create",
        "ServiceToken": "LambdaARN",
        "ResponseURL": "url",
        "StackId": "arn:aws:cloudformation:us-west-2:111122223333:stack/teststack/51af3dc0-da77-11e4-872e-1234567db123",
        "RequestId": "requestId",
        "ResourceType": "Custom::RegionRegistrationIsComplete",
        "LogicalResourceId": "CFNLogicalID",
        "PhysicalResourceId": "PhysicalID",
        "ResourceProperties": {"regions": ["us-east-1", "us-west-2"]},
    }


@fixture
def mocked_ssm_service() -> Iterator[MagicMock]:
    with patch(
        "instance_scheduler.handler.region_registration_events_iscomplete_handler.SSMService"
    ) as mock_ssm_class, patch(
        "instance_scheduler.handler.region_registration_events_iscomplete_handler.lambda_execution_role"
    ) as mock_lambda_role:

        mock_ssm_service = MagicMock()
        # Mock SSMService to return the same mock regardless of region parameter
        mock_ssm_class.return_value = mock_ssm_service
        mock_ssm_class.side_effect = lambda region=None: mock_ssm_service

        mock_assumed_role = MagicMock()
        mock_assumed_role.region = "us-east-1"
        mock_assumed_role.account = "123456789012"
        mock_lambda_role.return_value = mock_assumed_role

        yield mock_ssm_service


def test_create_request_complete(
    mocked_ssm_service: MagicMock,
    custom_resource_base_event: CustomResourceRequest[
        RegionRegistrationIsCompleteProperties
    ],
    mocked_environment: Mapping[str, str],
) -> None:
    # Mock SSM parameters showing all regions are managed
    mocked_ssm_service.get_parameters_by_path.return_value = [
        {"Name": "/instance-scheduler/namespace/regions/us-east-1", "Value": "managed"},
        {"Name": "/instance-scheduler/namespace/regions/us-west-2", "Value": "managed"},
    ]

    context = MockLambdaContext()
    logger = Logger()
    env = RegionRegistrationEnvironment.from_env()

    handler = RegionRegistrationIsCompleteHandler(
        custom_resource_base_event, context, logger, env
    )
    response = handler.handle_request()

    assert response["IsComplete"] is True
    mocked_ssm_service.get_parameters_by_path.assert_called_once_with(
        path="/instance-scheduler/namespace/regions/"
    )

    # Verify delete_parameter was called for the deleted region
    assert mocked_ssm_service.delete_parameter.call_count == 2


def test_create_request_incomplete(
    mocked_ssm_service: MagicMock,
    custom_resource_base_event: CustomResourceRequest[
        RegionRegistrationIsCompleteProperties
    ],
    mocked_environment: Mapping[str, str],
) -> None:
    # Mock SSM parameters showing one region is still being created
    mocked_ssm_service.get_parameters_by_path.return_value = [
        {"Name": "/instance-scheduler/namespace/regions/us-east-1", "Value": "created"},
        {"Name": "/instance-scheduler/namespace/regions/us-west-2", "Value": "managed"},
    ]

    context = MockLambdaContext()
    logger = Logger()
    env = RegionRegistrationEnvironment.from_env()

    handler = RegionRegistrationIsCompleteHandler(
        custom_resource_base_event, context, logger, env
    )
    response = handler.handle_request()

    assert response["IsComplete"] is False


def test_update_request_complete(
    mocked_ssm_service: MagicMock,
    mocked_environment: Mapping[str, str],
) -> None:
    event = {
        "RequestType": "Update",
        "ResourceProperties": {"regions": ["us-east-1", "eu-west-1"]},
        "OldResourceProperties": {"regions": ["us-east-1", "us-west-2"]},
        "StackId": "arn:aws:cloudformation:us-west-2:111122223333:stack/test-stack/51af3dc0-da77-11e4-872e-1234567db123",
        "RequestId": "test-request",
        "LogicalResourceId": "test-logical-id",
        "ResponseURL": "test-url",
    }

    # Mock SSM parameters showing correct states
    mocked_ssm_service.get_parameters_by_path.return_value = [
        {"Name": "/instance-scheduler/namespace/regions/us-east-1", "Value": "managed"},
        {"Name": "/instance-scheduler/namespace/regions/eu-west-1", "Value": "managed"},
        {"Name": "/instance-scheduler/namespace/regions/us-west-2", "Value": "deleted"},
    ]

    context = MockLambdaContext()
    logger = Logger()
    env = RegionRegistrationEnvironment.from_env()

    handler = RegionRegistrationIsCompleteHandler(event, context, logger, env)
    response = handler.handle_request()

    assert response["IsComplete"] is True
    # Verify delete_parameter was called for the deleted region(s)
    assert mocked_ssm_service.delete_parameter.call_count == 3


def test_update_request_incomplete(
    mocked_ssm_service: MagicMock,
    mocked_environment: Mapping[str, str],
) -> None:
    event = {
        "RequestType": "Update",
        "ResourceProperties": {"regions": ["us-east-1", "eu-west-1"]},
        "OldResourceProperties": {"regions": ["us-east-1", "us-west-2"]},
        "StackId": "arn:aws:cloudformation:us-west-2:111122223333:stack/test-stack/51af3dc0-da77-11e4-872e-1234567db123",
        "RequestId": "test-request",
        "LogicalResourceId": "test-logical-id",
        "ResponseURL": "test-url",
    }

    # Mock SSM parameters showing incomplete state
    mocked_ssm_service.get_parameters_by_path.return_value = [
        {"Name": "/instance-scheduler/namespace/regions/us-east-1", "Value": "managed"},
        {
            "Name": "/instance-scheduler/namespace/regions/eu-west-1",
            "Value": "created",
        },  # Still being created
        {
            "Name": "/instance-scheduler/namespace/regions/us-west-2",
            "Value": "deleting",
        },  # Still being deleted
    ]

    context = MockLambdaContext()
    logger = Logger()
    env = RegionRegistrationEnvironment.from_env()

    handler = RegionRegistrationIsCompleteHandler(event, context, logger, env)
    response = handler.handle_request()

    assert response["IsComplete"] is False
    # Verify delete_parameter was not called since deletion is not complete
    mocked_ssm_service.delete_parameter.assert_not_called()


def test_delete_request_complete(
    mocked_ssm_service: MagicMock,
    mocked_environment: Mapping[str, str],
) -> None:
    event = {
        "RequestType": "Delete",
        "ResourceProperties": {"regions": ["us-east-1", "us-west-2"]},
        "StackId": "arn:aws:cloudformation:us-west-2:111122223333:stack/test-stack/51af3dc0-da77-11e4-872e-1234567db123",
        "RequestId": "test-request",
        "LogicalResourceId": "test-logical-id",
        "ResponseURL": "test-url",
    }

    # Mock SSM parameters showing all regions are deleted
    mocked_ssm_service.get_parameters_by_path.return_value = [
        {"Name": "/instance-scheduler/namespace/regions/us-east-1", "Value": "deleted"},
        {"Name": "/instance-scheduler/namespace/regions/us-west-2", "Value": "deleted"},
    ]

    context = MockLambdaContext()
    logger = Logger()
    env = RegionRegistrationEnvironment.from_env()

    handler = RegionRegistrationIsCompleteHandler(event, context, logger, env)
    response = handler.handle_request()

    assert response["IsComplete"] is True
    # Verify delete_parameter was called for both regions
    assert mocked_ssm_service.delete_parameter.call_count == 2


def test_delete_request_incomplete(
    mocked_ssm_service: MagicMock,
    mocked_environment: Mapping[str, str],
) -> None:
    event = {
        "RequestType": "Delete",
        "ResourceProperties": {"regions": ["us-east-1", "us-west-2"]},
        "StackId": "arn:aws:cloudformation:us-west-2:111122223333:stack/test-stack/51af3dc0-da77-11e4-872e-1234567db123",
        "RequestId": "test-request",
        "LogicalResourceId": "test-logical-id",
        "ResponseURL": "test-url",
    }

    # Mock SSM parameters showing regions still being deleted
    mocked_ssm_service.get_parameters_by_path.return_value = [
        {
            "Name": "/instance-scheduler/namespace/regions/us-east-1",
            "Value": "deleting",
        },
        {
            "Name": "/instance-scheduler/namespace/regions/us-west-2",
            "Value": "deleting",
        },
    ]

    context = MockLambdaContext()
    logger = Logger()
    env = RegionRegistrationEnvironment.from_env()

    handler = RegionRegistrationIsCompleteHandler(event, context, logger, env)
    response = handler.handle_request()

    assert response["IsComplete"] is False
    # Verify delete_parameter was not called since deletion is not complete
    mocked_ssm_service.delete_parameter.assert_not_called()


def test_create_request_empty_regions_uses_default(
    mocked_ssm_service: MagicMock,
    mocked_environment: Mapping[str, str],
) -> None:
    event = {
        "RequestType": "Create",
        "ResourceProperties": {"regions": []},
        "StackId": "arn:aws:cloudformation:us-west-2:111122223333:stack/test-stack/51af3dc0-da77-11e4-872e-1234567db123",
        "RequestId": "test-request",
        "LogicalResourceId": "test-logical-id",
        "ResponseURL": "test-url",
    }

    # Mock SSM parameters showing default region is managed
    mocked_ssm_service.get_parameters_by_path.return_value = [
        {"Name": "/instance-scheduler/namespace/regions/us-east-1", "Value": "managed"},
    ]

    context = MockLambdaContext()
    logger = Logger()
    env = RegionRegistrationEnvironment.from_env()

    handler = RegionRegistrationIsCompleteHandler(event, context, logger, env)
    response = handler.handle_request()

    assert response["IsComplete"] is True
