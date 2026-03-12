# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from contextlib import contextmanager
from typing import Any, Callable, Iterator, Mapping
from unittest.mock import MagicMock, patch

from aws_lambda_powertools.utilities.typing import LambdaContext
from tests.test_utils.mock_environs.mock_environment import MockEnvironment


@contextmanager
def mock_forward_sqs_messages_to_lambda_handler(
    lambda_handler: Callable[[Mapping[str, Any], LambdaContext], Any],
    lambda_env: MockEnvironment,
) -> Iterator[None]:
    """Context manager that intercepts SQS send_message_to_queue calls and invokes lambda handler synchronously."""

    def mock_send_message(
        queue_url: str, delay_in_seconds: int, message_body: str
    ) -> str:
        # Create SQS event structure that lambda handler expects
        sqs_event = {"Records": [{"body": message_body}]}

        with lambda_env.patch_env():
            # Create mock lambda context
            lambda_context = MagicMock(spec=LambdaContext)

            # Invoke handler synchronously
            lambda_handler(sqs_event, lambda_context)
            return "mock-message-id"

    # Patch use in ec2 service (only place this is used at time of writing). This does not work generally yet
    with patch(
        "instance_scheduler.scheduling.ec2.ec2.send_message_to_queue",
        side_effect=mock_send_message,
    ):
        yield
