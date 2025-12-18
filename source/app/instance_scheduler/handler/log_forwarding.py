# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import base64
import gzip
import json
from typing import TYPE_CHECKING, Any, Mapping

from instance_scheduler.handler.environments.log_forwarding_environment import (
    LogForwardingEnvironment,
)
from instance_scheduler.observability.powertools_logging import powertools_logger
from instance_scheduler.util.session_manager import lambda_execution_role

if TYPE_CHECKING:
    from aws_lambda_powertools.utilities.typing import LambdaContext
else:
    LambdaContext = object

logger = powertools_logger()
sns = lambda_execution_role().client("sns")


@logger.inject_lambda_context(log_event=True)
def handle_log_event(event: Mapping[str, Any], _context: LambdaContext) -> None:
    env = LogForwardingEnvironment.from_env()

    compressed_payload = base64.b64decode(event["awslogs"]["data"])
    uncompressed_payload = gzip.decompress(compressed_payload)
    log_data = json.loads(uncompressed_payload)

    log_messages = [
        json.loads(log_event["message"]) for log_event in log_data["logEvents"]
    ]

    sns.publish(
        TopicArn=env.sns_notification_topic,
        Message=json.dumps(log_messages, indent=2),
        Subject="CloudWatch Log Event",
    )
