# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

import json
from os import environ
from typing import Iterator, Mapping
from unittest.mock import MagicMock, patch

import pytest
from _pytest.fixtures import fixture
from aws_lambda_powertools import Logger

from instance_scheduler.handler.environments.remote_registration_environment import (
    RemoteRegistrationEnvironment,
)
from instance_scheduler.handler.remote_registration_custom_resource import (
    RemoteRegistrationCustomResourceHandler,
    RemoteRegistrationProperties,
    handle_remote_registration_request,
)
from instance_scheduler.util.app_env_utils import AppEnvError
from instance_scheduler.util.custom_resource import CustomResourceRequest
from tests.context import MockLambdaContext


@fixture
def mocked_environment() -> Iterator[Mapping[str, str]]:
    mocked_environment = {
        "USER_AGENT_EXTRA": "test-user-agent-extra",
        "HUB_REGISTRATION_LAMBDA_ARN": "arn:aws:lambda:us-east-1:111122223333:function:Test-SpokeRegistration",
    }
    with patch.dict(environ, mocked_environment, clear=True):
        yield mocked_environment


@fixture
def custom_resource_base_event() -> CustomResourceRequest[RemoteRegistrationProperties]:
    return {
        "RequestType": "Create",
        "ServiceToken": "LambdaARN",
        "ResponseURL": "url",
        "StackId": "arn:aws:cloudformation:us-west-2:123456789012:stack/teststack/51af3dc0-da77-11e4-872e-1234567db123",
        "RequestId": "requestId",
        "ResourceType": "Custom::RegisterSpokeAccount",
        "LogicalResourceId": "CFNLogicalID",
        "PhysicalResourceId": "PhysicalID",
        "ResourceProperties": {},
        "OldResourceProperties": {},
    }


@fixture
def custom_resource_create_event(
    custom_resource_base_event: CustomResourceRequest[RemoteRegistrationProperties],
) -> CustomResourceRequest[RemoteRegistrationProperties]:
    custom_resource_base_event["RequestType"] = "Create"
    return custom_resource_base_event


@fixture
def custom_resource_update_event(
    custom_resource_base_event: CustomResourceRequest[RemoteRegistrationProperties],
) -> CustomResourceRequest[RemoteRegistrationProperties]:
    custom_resource_base_event["RequestType"] = "Update"
    return custom_resource_base_event


@fixture
def custom_resource_delete_event(
    custom_resource_base_event: CustomResourceRequest[RemoteRegistrationProperties],
) -> CustomResourceRequest[RemoteRegistrationProperties]:
    custom_resource_base_event["RequestType"] = "Delete"
    return custom_resource_base_event


@fixture
def mocked_lambda_invoke() -> Iterator[MagicMock]:
    with patch.object(
        RemoteRegistrationCustomResourceHandler, "_lambda_client"
    ) as lambda_client:
        with patch.object(lambda_client, "invoke") as invoke_func:
            yield invoke_func


@patch.object(RemoteRegistrationCustomResourceHandler, "_send_response")
def test_remote_registration_custom_resource_create(
    mocked_cfn_callback: MagicMock,
    mocked_lambda_invoke: MagicMock,
    mocked_environment: Mapping[str, str],
    custom_resource_create_event: CustomResourceRequest[RemoteRegistrationProperties],
) -> None:
    function_arn = (
        "arn:aws:lambda:us-east-1:111122223333:function:Test-SpokeRegistration"
    )
    context = MockLambdaContext()
    logger = Logger()
    env = RemoteRegistrationEnvironment(
        user_agent_extra="UserAgentExtra", hub_registration_lambda_arn=function_arn
    )

    handler = RemoteRegistrationCustomResourceHandler(
        custom_resource_create_event, context, logger, env
    )
    handler.handle_request()
    assert mocked_lambda_invoke.call_args.kwargs["FunctionName"] == function_arn
    assert mocked_lambda_invoke.call_args.kwargs["Payload"] == str.encode(
        json.dumps({"account": "123456789012", "operation": "Register"})
    )

    response = mocked_cfn_callback.call_args.args[0]
    assert response["Status"] == "SUCCESS", response["Reason"]


@patch.object(RemoteRegistrationCustomResourceHandler, "_send_response")
def test_remote_registration_custom_resource_update(
    mocked_cfn_callback: MagicMock,
    mocked_environment: Mapping[str, str],
    custom_resource_update_event: CustomResourceRequest[RemoteRegistrationProperties],
) -> None:
    function_arn = (
        "arn:aws:lambda:us-east-1:111122223333:function:Test-SpokeRegistration"
    )
    context = MockLambdaContext()
    logger = Logger()
    env = RemoteRegistrationEnvironment(
        user_agent_extra="UserAgentExtra", hub_registration_lambda_arn=function_arn
    )

    handler = RemoteRegistrationCustomResourceHandler(
        custom_resource_update_event, context, logger, env
    )
    handler.handle_request()

    response = mocked_cfn_callback.call_args.args[0]
    assert response["Status"] == "SUCCESS", response["Reason"]


@patch.object(RemoteRegistrationCustomResourceHandler, "_send_response")
def test_remote_registration_custom_resource_delete(
    mocked_cfn_callback: MagicMock,
    mocked_lambda_invoke: MagicMock,
    mocked_environment: Mapping[str, str],
    custom_resource_delete_event: CustomResourceRequest[RemoteRegistrationProperties],
) -> None:
    function_arn = (
        "arn:aws:lambda:us-east-1:111122223333:function:Test-SpokeRegistration"
    )
    context = MockLambdaContext()
    logger = Logger()
    env = RemoteRegistrationEnvironment(
        user_agent_extra="UserAgentExtra", hub_registration_lambda_arn=function_arn
    )

    handler = RemoteRegistrationCustomResourceHandler(
        custom_resource_delete_event, context, logger, env
    )
    handler.handle_request()

    assert mocked_lambda_invoke.call_args.kwargs["FunctionName"] == function_arn
    assert mocked_lambda_invoke.call_args.kwargs["Payload"] == str.encode(
        json.dumps({"account": "123456789012", "operation": "Deregister"})
    )

    response = mocked_cfn_callback.call_args.args[0]
    assert response["Status"] == "SUCCESS", response["Reason"]


def test_remote_registration_from_env(
    mocked_environment: Mapping[str, str],
) -> None:
    env = RemoteRegistrationEnvironment.from_env()
    assert env.user_agent_extra == mocked_environment["USER_AGENT_EXTRA"]
    assert (
        env.hub_registration_lambda_arn
        == mocked_environment["HUB_REGISTRATION_LAMBDA_ARN"]
    )


def test_remote_registration_missing_env_var() -> None:
    mocked_environment = {
        "USER_AGENT_EXTRA": "test-user-agent-extra",
    }
    with patch.dict(environ, mocked_environment, clear=True):
        with pytest.raises(AppEnvError):
            RemoteRegistrationEnvironment.from_env()


def test_remote_registration_sends_cfn_response(
    custom_resource_base_event: CustomResourceRequest[RemoteRegistrationProperties],
) -> None:
    with patch(
        "instance_scheduler.handler.remote_registration_custom_resource.http"
    ) as mocked_http:
        context = MockLambdaContext()
        handle_remote_registration_request(custom_resource_base_event, context)
        mocked_http.request.assert_called_once_with(
            "PUT",
            custom_resource_base_event.get("ResponseURL"),
            headers={"Content-Type": "application/json"},
            body=json.dumps(
                {
                    "Status": "FAILED",
                    "Reason": "Response sent to cloudformation to prevent hung resource",
                    "PhysicalResourceId": custom_resource_base_event.get(
                        "LogicalResourceId"
                    ),
                    "StackId": custom_resource_base_event.get("StackId"),
                    "RequestId": custom_resource_base_event.get("RequestId"),
                    "LogicalResourceId": custom_resource_base_event.get(
                        "LogicalResourceId"
                    ),
                }
            ),
        )
