# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from typing import TYPE_CHECKING

from instance_scheduler.util.session_manager import lambda_execution_role

if TYPE_CHECKING:
    from mypy_boto3_sqs import SQSClient
    from mypy_boto3_sqs.type_defs import SendMessageResultTypeDef
else:
    SQSClient = object
    SendMessageResultTypeDef = object


def send_message_to_queue(
    queue_url: str, delay_in_seconds: int, message_body: str
) -> str:
    """
    Send a message to an SQS queue.

    Args:
        queue_url: The URL of the SQS queue
        message_body: The message body to send

    Returns:
        The MessageId of the sent message
    """
    sqs_client: SQSClient = lambda_execution_role().client("sqs")

    response: SendMessageResultTypeDef = sqs_client.send_message(
        QueueUrl=queue_url, DelaySeconds=delay_in_seconds, MessageBody=message_body
    )

    return response["MessageId"]
