# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import uuid
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch
from uuid import UUID

import boto3

from instance_scheduler.handler.metrics_uuid_custom_resource import (
    CreateUuidRequest,
    MetricsUuidCustomResource,
    handle_metrics_uuid_request,
)
from instance_scheduler.util.custom_resource import (
    CustomResourceRequest,
    CustomResourceResponse,
)
from tests.context import MockLambdaContext
from tests.test_utils.mock_metrics_uuid_environment import MockMetricsUuidEnviron

if TYPE_CHECKING:
    from mypy_boto3_ssm.client import SSMClient
else:
    SSMClient = object

stack_arn = "arn:aws:cloudformation:us-west-2:123456789012:stack/teststack/51af3dc0-da77-11e4-872e-1234567db123"


def new_create_request() -> CustomResourceRequest[CreateUuidRequest]:
    return {
        "RequestType": "Create",
        "ServiceToken": "LambdaARN",
        "ResponseURL": "url",
        "StackId": stack_arn,
        "RequestId": "requestId",
        "ResourceType": "Custom::ServiceInstanceSchedule",
        "LogicalResourceId": "CFNLogicalID",
        "PhysicalResourceId": "PhysicalID",
        "ResourceProperties": {},
        "OldResourceProperties": {},
    }


@patch.object(MetricsUuidCustomResource, "_send_response")
def test_metrics_uuid_generates_new_uuid_when_one_not_present(
    mocked_cfn_callback: MagicMock, moto_backend: None
) -> None:
    with MockMetricsUuidEnviron():
        event = new_create_request()
        handle_metrics_uuid_request(event, MockLambdaContext())

        response: CustomResourceResponse = mocked_cfn_callback.call_args.args[0]
        assert response["Status"] == "SUCCESS"
        assert "Uuid" in response["Data"]
        assert UUID(response["Data"]["Uuid"]) is not None  # is a valid uuid


@patch.object(MetricsUuidCustomResource, "_send_response")
def test_metrics_uuid_uses_existing_uuid_when_one_is_present(
    mocked_cfn_callback: MagicMock,
    moto_backend: None,
) -> None:
    with MockMetricsUuidEnviron() as env:
        existing_uuid = uuid.uuid4()
        stack_id = env.stack_id[-36:]
        uuid_key = env.uuid_key + str(stack_id)
        ssm_client: SSMClient = boto3.client("ssm")
        ssm_client.put_parameter(
            Name=uuid_key,
            Description="metrics uuid as stored in v1.5.3 and below",
            Value=str(existing_uuid),
            Type="String",
        )

        event = new_create_request()
        handle_metrics_uuid_request(event, MockLambdaContext())

        response: CustomResourceResponse = mocked_cfn_callback.call_args.args[0]
        assert response["Status"] == "SUCCESS"
        assert "Uuid" in response["Data"]
        assert UUID(response["Data"]["Uuid"]) == existing_uuid
