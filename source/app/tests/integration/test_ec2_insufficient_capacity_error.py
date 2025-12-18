# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import json
from contextlib import contextmanager
from typing import Iterator
from unittest.mock import Mock

import boto3
import pytest
from botocore.exceptions import ClientError
from instance_scheduler.configuration.scheduling_context import SchedulingContext
from instance_scheduler.scheduling.ec2.ice_retry import IceRetryRequest
from instance_scheduler.util.session_manager import lambda_execution_role
from tests.integration.helpers.boto_client_helpers import mock_specific_client
from tests.integration.helpers.ec2_helpers import (
    start_ec2_instances,
    stop_ec2_instances,
)
from tests.integration.helpers.run_handler import simple_schedule
from tests.integration.helpers.schedule_helpers import quick_time
from tests.test_utils.mock_scheduling_request_environment import (
    MockSchedulingRequestEnvironment,
)


def willRaise(ex: Exception) -> None:
    raise ex


@contextmanager
def ec2_client_will_raise_insufficient_capacity_error() -> Iterator[None]:
    with mock_specific_client("ec2") as ec2_client:
        original_start_instances = ec2_client.start_instances
        ec2_client.start_instances.side_effect = ClientError(
            {
                "Error": {
                    "Code": "InsufficientInstanceCapacity",
                    "Message": "Insufficient capacity",
                }
            },
            "StartInstances",
        )
        try:
            yield
        finally:
            ec2_client.start_instances = original_start_instances


@pytest.fixture
def mock_sqs_client() -> Iterator[Mock]:
    with mock_specific_client("sqs") as sqs_client:
        sqs_client.send_message = Mock(return_value={"MessageId": "test-message-id"})
        yield sqs_client


def test_ice_helper(ec2_instance: str) -> None:
    stop_ec2_instances(ec2_instance)
    with (
        ec2_client_will_raise_insufficient_capacity_error(),
        pytest.raises(ClientError),
    ):
        start_ec2_instances(ec2_instance)


def test_insufficient_capacity_error_sends_retry_requests(
    ec2_instance: str, scheduling_context: SchedulingContext, mock_sqs_client: Mock
) -> None:
    """Test that InsufficientInstanceCapacity error with alternate types sends message to SQS"""
    stop_ec2_instances(ec2_instance)

    # Add alternate instance types tag
    ec2_client = boto3.client("ec2")
    ec2_client.create_tags(
        Resources=[ec2_instance],
        Tags=[
            {
                "Key": "IS-PreferredInstanceTypes",
                "Value": "m1.small,t3.medium",  # m1 small is default used by m oto
            }
        ],
    )

    env = MockSchedulingRequestEnvironment(
        ice_retry_queue_url="https://sqs.us-east-1.amazonaws.com/111122223333/test-queue"
    )

    with (
        simple_schedule(begintime="10:00", endtime="20:00") as context,
        ec2_client_will_raise_insufficient_capacity_error(),
    ):
        context.run_scheduling_request_handler(dt=quick_time(15, 0), environment=env)

        assert mock_sqs_client.send_message.called
        call_args = mock_sqs_client.send_message.call_args
        assert call_args.kwargs["QueueUrl"] == env.ice_retry_queue_url
        assert call_args.kwargs["MessageBody"] == json.dumps(
            IceRetryRequest(
                account=lambda_execution_role().account,
                region=lambda_execution_role().region,
                instance_id=ec2_instance,
                preferred_instance_types=[
                    "m1.small",
                    "t3.medium",
                ],
            )
        )


def test_instance_using_non_preferred_type_sends_ice_request(
    ec2_instance: str, scheduling_context: SchedulingContext, mock_sqs_client: Mock
) -> None:
    """Test that InsufficientInstanceCapacity error with alternate types sends message to SQS"""
    stop_ec2_instances(ec2_instance)

    # Add alternate instance types tag
    ec2_client = boto3.client("ec2")
    ec2_client.create_tags(
        Resources=[ec2_instance],
        Tags=[
            {
                "Key": "IS-PreferredInstanceTypes",
                "Value": "t3.medium, m1.small",  # m1 small is default used by moto
            }
        ],
    )

    env = MockSchedulingRequestEnvironment(
        ice_retry_queue_url="https://sqs.us-east-1.amazonaws.com/111122223333/test-queue"
    )

    with simple_schedule(begintime="10:00", endtime="20:00") as context:
        context.run_scheduling_request_handler(dt=quick_time(15, 0), environment=env)

        assert mock_sqs_client.send_message.called
        call_args = mock_sqs_client.send_message.call_args
        assert call_args.kwargs["QueueUrl"] == env.ice_retry_queue_url
        assert call_args.kwargs["MessageBody"] == json.dumps(
            IceRetryRequest(
                account=lambda_execution_role().account,
                region=lambda_execution_role().region,
                instance_id=ec2_instance,
                preferred_instance_types=["t3.medium", "m1.small"],
            )
        )


def test_insufficient_capacity_error_does_not_send_request_if_no_preferred_types_specified(
    ec2_instance: str, scheduling_context: SchedulingContext, mock_sqs_client: Mock
) -> None:
    """Test that InsufficientInstanceCapacity error without alternate types doesn't send to queue"""
    stop_ec2_instances(ec2_instance)

    env = MockSchedulingRequestEnvironment(
        ice_retry_queue_url="https://sqs.us-east-1.amazonaws.com/111122223333/test-queue"
    )

    with (
        simple_schedule(begintime="10:00", endtime="20:00") as context,
        ec2_client_will_raise_insufficient_capacity_error(),
    ):
        context.run_scheduling_request_handler(dt=quick_time(10, 0), environment=env)

        assert not mock_sqs_client.send_message.called
