# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from aws_lambda_powertools.utilities.typing import LambdaContext


class MockLambdaContext(LambdaContext):
    def __init__(self, log_group_name: str = "logGroupName") -> None:
        self._aws_request_id = "requestId"
        self._log_group_name = log_group_name
        self._log_stream_name = "logStreamName"
        self._function_name = "functionName"
        self._memory_limit_in_mb = 128
        self._function_version = "$LATEST"
        self._invoked_function_arn = (
            "arn:aws:lambda:us-east-1:123456789012:function:functionName"
        )

    @staticmethod
    def get_remaining_time_in_millis() -> int:
        return 2000
