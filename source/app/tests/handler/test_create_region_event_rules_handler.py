# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

import json
from os import environ
from typing import Iterator, Mapping
from unittest.mock import MagicMock, patch

import pytest
from _pytest.fixtures import fixture
from aws_lambda_powertools import Logger
from botocore.exceptions import ClientError
from instance_scheduler.handler.create_region_event_rules_handler import (
    CreateRegionEventRulesHandler,
    CreateRegionEventRulesProperties,
    lambda_handler,
)
from instance_scheduler.handler.environments.create_region_event_rules_environment import (
    CreateRegionEventRulesEnvironment,
)
from instance_scheduler.util.app_env_utils import AppEnvError
from instance_scheduler.util.custom_resource import CustomResourceRequest
from tests.context import MockLambdaContext


@fixture
def mocked_environment() -> Iterator[Mapping[str, str]]:
    mocked_environment = {
        "TAGGING_EVENT_RULE_ROLE_ARN": "arn:aws:iam::111122223333:role/test-role",
        "TAGGING_EVENT_BUS_ARN": "arn:aws:events:us-east-1:111122223333:event-bus/test-bus",
        "SCHEDULE_TAG_KEY": "Schedule",
        "EVENT_RULE_PREFIX": "test-prefix",
        "USER_AGENT_EXTRA": "test-user-agent-extra",
        "POWERTOOLS_SERVICE_NAME": "test-service",
        "VERSION": "1.0.0",
        "REGIONAL_EVENT_BUS_NAME": "test-regional-bus",
    }
    with patch.dict(environ, mocked_environment, clear=True):
        yield mocked_environment


@fixture
def custom_resource_base_event() -> (
    CustomResourceRequest[CreateRegionEventRulesProperties]
):
    return {
        "RequestType": "Create",
        "ServiceToken": "LambdaARN",
        "ResponseURL": "url",
        "StackId": "arn:aws:cloudformation:us-west-2:111122223333:stack/teststack/51af3dc0-da77-11e4-872e-1234567db123",
        "RequestId": "requestId",
        "ResourceType": "Custom::SetupRegionalEvents",
        "LogicalResourceId": "CFNLogicalID",
        "PhysicalResourceId": "PhysicalID",
        "ResourceProperties": {"regions": ["us-east-1", "us-west-2"]},
    }


@fixture
def mocked_events_client() -> Iterator[MagicMock]:
    mock_events_client = MagicMock()
    with patch(
        "instance_scheduler.handler.create_region_event_rules_handler.lambda_execution_role"
    ) as mock_lambda_role:
        mock_assumed_role = MagicMock()
        mock_assumed_role.client.return_value = mock_events_client
        mock_assumed_role.region = "us-east-1"
        mock_lambda_role.return_value = mock_assumed_role
        yield mock_events_client


@patch.object(CreateRegionEventRulesHandler, "_send_response")
def test_create_event_rules_success(
    mocked_cfn_callback: MagicMock,
    mocked_events_client: MagicMock,
    custom_resource_base_event: CustomResourceRequest[CreateRegionEventRulesProperties],
    mocked_environment: Mapping[str, str],
) -> None:
    context = MockLambdaContext()
    logger = Logger()
    env = CreateRegionEventRulesEnvironment.from_env()

    handler = CreateRegionEventRulesHandler(
        custom_resource_base_event, context, logger, env
    )
    handler.handle_request()

    # Verify put_rule was called for both ASG and resource tagging rules in both regions
    assert mocked_events_client.put_rule.call_count == 4
    assert mocked_events_client.put_targets.call_count == 4

    mocked_cfn_callback.assert_called_once()
    response = mocked_cfn_callback.call_args[0][0]
    assert response["Status"] == "SUCCESS", response.get("Reason", "")
    assert response["Data"]["REGIONAL_BUS_NAME"] == "test-regional-bus"


@patch.object(CreateRegionEventRulesHandler, "_send_response")
def test_update_event_rules_success(
    mocked_cfn_callback: MagicMock,
    mocked_events_client: MagicMock,
    mocked_environment: Mapping[str, str],
) -> None:
    event = {
        "RequestType": "Update",
        "ResourceProperties": {"regions": ["us-east-1", "us-west-2"]},
        "OldResourceProperties": {"regions": ["us-east-1"]},
        "StackId": "arn:aws:cloudformation:us-west-2:111122223333:stack/test-stack/51af3dc0-da77-11e4-872e-1234567db123",
        "RequestId": "test-request",
        "LogicalResourceId": "test-logical-id",
        "ResponseURL": "test-url",
    }

    context = MockLambdaContext()
    logger = Logger()
    env = CreateRegionEventRulesEnvironment.from_env()

    handler = CreateRegionEventRulesHandler(event, context, logger, env)
    handler.handle_request()

    # Verify delete operations for old regions and create for new regions
    assert mocked_events_client.remove_targets.call_count == 2  # Old region cleanup
    assert mocked_events_client.delete_rule.call_count == 2  # Old region cleanup
    assert mocked_events_client.put_rule.call_count == 4  # New regions setup
    assert mocked_events_client.put_targets.call_count == 4  # New regions setup

    mocked_cfn_callback.assert_called_once()
    response = mocked_cfn_callback.call_args[0][0]
    assert response["Status"] == "SUCCESS", response.get("Reason", "")


@patch.object(CreateRegionEventRulesHandler, "_send_response")
def test_delete_event_rules_success(
    mocked_cfn_callback: MagicMock,
    mocked_events_client: MagicMock,
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

    context = MockLambdaContext()
    logger = Logger()
    env = CreateRegionEventRulesEnvironment.from_env()

    handler = CreateRegionEventRulesHandler(event, context, logger, env)
    handler.handle_request()

    # Verify delete operations for both regions
    assert mocked_events_client.remove_targets.call_count == 4
    assert mocked_events_client.delete_rule.call_count == 4

    mocked_cfn_callback.assert_called_once()
    response = mocked_cfn_callback.call_args[0][0]
    assert response["Status"] == "SUCCESS", response.get("Reason", "")


@patch.object(CreateRegionEventRulesHandler, "_send_response")
def test_create_event_rules_client_error_rollback(
    mocked_cfn_callback: MagicMock,
    mocked_events_client: MagicMock,
    custom_resource_base_event: CustomResourceRequest[CreateRegionEventRulesProperties],
    mocked_environment: Mapping[str, str],
) -> None:
    # Mock client error on second region
    mocked_events_client.put_rule.side_effect = [
        None,
        None,
        None,
        ClientError(
            {"Error": {"Code": "TestError", "Message": "Test error"}}, "put_rule"
        ),
    ]

    context = MockLambdaContext()
    logger = Logger()
    env = CreateRegionEventRulesEnvironment.from_env()

    handler = CreateRegionEventRulesHandler(
        custom_resource_base_event, context, logger, env
    )
    handler.handle_request()

    # Verify rollback operations were called
    assert mocked_events_client.remove_targets.call_count >= 2
    assert mocked_events_client.delete_rule.call_count >= 2

    mocked_cfn_callback.assert_called_once()
    response = mocked_cfn_callback.call_args[0][0]
    assert response["Status"] == "FAILED"


def test_rule_name_generation(
    mocked_environment: Mapping[str, str],
) -> None:
    context = MockLambdaContext()
    logger = Logger()
    env = CreateRegionEventRulesEnvironment.from_env()

    event = {
        "RequestType": "Create",
        "ResourceProperties": {"regions": ["us-east-1"]},
        "StackId": "arn:aws:cloudformation:us-west-2:111122223333:stack/test-stack/51af3dc0-da77-11e4-872e-1234567db123",
        "RequestId": "test-request",
        "LogicalResourceId": "test-logical-id",
    }

    handler = CreateRegionEventRulesHandler(event, context, logger, env)

    asg_rule_name = handler._get_asg_rule_name()
    resource_rule_name = handler._get_resource_rule_name()

    assert asg_rule_name == "test-prefix-asg-tagging"
    assert resource_rule_name == "test-prefix-resource-tagging"


def test_environment_from_env(
    mocked_environment: Mapping[str, str],
) -> None:
    env = CreateRegionEventRulesEnvironment.from_env()
    assert (
        env.tagging_event_rule_role_arn
        == mocked_environment["TAGGING_EVENT_RULE_ROLE_ARN"]
    )
    assert env.tagging_event_bus_arn == mocked_environment["TAGGING_EVENT_BUS_ARN"]
    assert env.version == mocked_environment["VERSION"]
    assert env.tagging_event_rule_name_prefix == mocked_environment["EVENT_RULE_PREFIX"]
    assert env.schedule_tag_key == mocked_environment["SCHEDULE_TAG_KEY"]
    assert env.regional_event_bus_name == mocked_environment["REGIONAL_EVENT_BUS_NAME"]


def test_environment_missing_env_var() -> None:
    mocked_environment = {
        "USER_AGENT_EXTRA": "test-user-agent-extra",
    }
    with patch.dict(environ, mocked_environment, clear=True):
        with pytest.raises(AppEnvError):
            CreateRegionEventRulesEnvironment.from_env()


@patch("instance_scheduler.handler.create_region_event_rules_handler.http")
def test_lambda_handler_sends_cfn_response(
    mock_http: MagicMock,
    custom_resource_base_event: CustomResourceRequest[CreateRegionEventRulesProperties],
    mocked_environment: Mapping[str, str],
) -> None:
    custom_resource_base_event["ResponseURL"] = "https://test-url.com"

    with patch(
        "instance_scheduler.handler.environments.create_region_event_rules_environment.CreateRegionEventRulesEnvironment.from_env"
    ) as mock_env:
        mock_env.side_effect = Exception("Test error")

        context = MockLambdaContext()
        lambda_handler(custom_resource_base_event, context)

        mock_http.request.assert_called_once()
        call_args = mock_http.request.call_args
        assert call_args[0][0] == "PUT"
        assert call_args[0][1] == "https://test-url.com"

        response_body = json.loads(call_args[1]["body"])
        assert response_body["Status"] == "FAILED"


@patch.object(CreateRegionEventRulesHandler, "_send_response")
def test_create_regional_event_bus_success(
    mocked_cfn_callback: MagicMock,
    mocked_events_client: MagicMock,
    mocked_environment: Mapping[str, str],
) -> None:
    event = {
        "RequestType": "Create",
        "ResourceProperties": {"regions": ["us-east-1"]},
        "StackId": "arn:aws:cloudformation:us-west-2:111122223333:stack/test-stack/51af3dc0-da77-11e4-872e-1234567db123",
        "RequestId": "test-request",
        "LogicalResourceId": "test-logical-id",
    }

    context = MockLambdaContext()
    logger = Logger()
    env = CreateRegionEventRulesEnvironment.from_env()

    handler = CreateRegionEventRulesHandler(event, context, logger, env)
    handler.handle_request()

    mocked_events_client.create_event_bus.assert_called_once_with(
        Name="test-regional-bus"
    )


@patch.object(CreateRegionEventRulesHandler, "_send_response")
def test_create_regional_event_bus_already_exists(
    mocked_cfn_callback: MagicMock,
    mocked_events_client: MagicMock,
    mocked_environment: Mapping[str, str],
) -> None:
    mocked_events_client.create_event_bus.side_effect = ClientError(
        {"Error": {"Code": "ResourceAlreadyExistsException", "Message": "Bus exists"}},
        "create_event_bus",
    )

    event = {
        "RequestType": "Create",
        "ResourceProperties": {"regions": ["us-east-1"]},
        "StackId": "arn:aws:cloudformation:us-west-2:111122223333:stack/test-stack/51af3dc0-da77-11e4-872e-1234567db123",
        "RequestId": "test-request",
        "LogicalResourceId": "test-logical-id",
    }

    context = MockLambdaContext()
    logger = Logger()
    env = CreateRegionEventRulesEnvironment.from_env()

    handler = CreateRegionEventRulesHandler(event, context, logger, env)
    handler.handle_request()

    mocked_cfn_callback.assert_called_once()
    response = mocked_cfn_callback.call_args[0][0]
    assert response["Status"] == "SUCCESS"


@patch.object(CreateRegionEventRulesHandler, "_send_response")
def test_delete_regional_event_bus_not_found(
    mocked_cfn_callback: MagicMock,
    mocked_events_client: MagicMock,
    mocked_environment: Mapping[str, str],
) -> None:
    mocked_events_client.delete_event_bus.side_effect = ClientError(
        {"Error": {"Code": "ResourceNotFoundException", "Message": "Bus not found"}},
        "delete_event_bus",
    )

    event = {
        "RequestType": "Delete",
        "ResourceProperties": {"regions": ["us-east-1"]},
        "StackId": "arn:aws:cloudformation:us-west-2:111122223333:stack/test-stack/51af3dc0-da77-11e4-872e-1234567db123",
        "RequestId": "test-request",
        "LogicalResourceId": "test-logical-id",
    }

    context = MockLambdaContext()
    logger = Logger()
    env = CreateRegionEventRulesEnvironment.from_env()

    handler = CreateRegionEventRulesHandler(event, context, logger, env)
    handler.handle_request()

    mocked_cfn_callback.assert_called_once()
    response = mocked_cfn_callback.call_args[0][0]
    assert response["Status"] == "SUCCESS"


@patch.object(CreateRegionEventRulesHandler, "_send_response")
def test_delete_request_returns_regional_bus_name(
    mocked_cfn_callback: MagicMock,
    mocked_events_client: MagicMock,
    mocked_environment: Mapping[str, str],
) -> None:
    event = {
        "RequestType": "Delete",
        "ResourceProperties": {"regions": ["us-east-1"]},
        "StackId": "arn:aws:cloudformation:us-west-2:111122223333:stack/test-stack/51af3dc0-da77-11e4-872e-1234567db123",
        "RequestId": "test-request",
        "LogicalResourceId": "test-logical-id",
    }

    context = MockLambdaContext()
    logger = Logger()
    env = CreateRegionEventRulesEnvironment.from_env()

    handler = CreateRegionEventRulesHandler(event, context, logger, env)
    handler.handle_request()

    mocked_cfn_callback.assert_called_once()
    response = mocked_cfn_callback.call_args[0][0]
    assert response["Status"] == "SUCCESS"
    assert response["Data"]["REGIONAL_BUS_NAME"] == "test-regional-bus"


@patch.object(CreateRegionEventRulesHandler, "_send_response")
def test_empty_regions_uses_default(
    mocked_cfn_callback: MagicMock,
    mocked_events_client: MagicMock,
    mocked_environment: Mapping[str, str],
) -> None:
    event = {
        "RequestType": "Create",
        "ResourceProperties": {"regions": []},
        "StackId": "arn:aws:cloudformation:us-west-2:111122223333:stack/test-stack/51af3dc0-da77-11e4-872e-1234567db123",
        "RequestId": "test-request",
        "LogicalResourceId": "test-logical-id",
    }

    with patch(
        "instance_scheduler.handler.create_region_event_rules_handler.lambda_execution_role"
    ) as mock_lambda_role:
        mock_assumed_role = MagicMock()
        mock_assumed_role.client.return_value = mocked_events_client
        mock_assumed_role.region = "us-east-1"
        mock_lambda_role.return_value = mock_assumed_role

        context = MockLambdaContext()
        logger = Logger()
        env = CreateRegionEventRulesEnvironment.from_env()

        handler = CreateRegionEventRulesHandler(event, context, logger, env)
        handler.handle_request()

        assert mocked_events_client.put_rule.call_count == 2
        assert mocked_events_client.put_targets.call_count == 2

        mocked_cfn_callback.assert_called_once()
        response = mocked_cfn_callback.call_args[0][0]
        assert response["Status"] == "SUCCESS"
        assert response["Data"]["REGIONAL_BUS_NAME"] == "test-regional-bus"
