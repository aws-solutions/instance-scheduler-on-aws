# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import os
from unittest.mock import MagicMock, patch

from aws_lambda_powertools.utilities.typing import LambdaContext

from instance_scheduler import main
from instance_scheduler.main import lambda_handler
from instance_scheduler.util.logger import Logger


@patch.object(Logger, "client")  # stops logger from slowing down the test
def test_correct_handler_called(logger_client: MagicMock) -> None:
    mock_handler = MagicMock()
    mock_handler.is_handling_request.return_value = True
    my_response = "Everything's great!"
    mock_handler.return_value.handle_request.return_value = my_response
    mock_handler.__name__ = "my-handler"

    with patch.dict(
        os.environ,
        {
            "LOG_GROUP": "log-group-name",
            "ISSUES_TOPIC_ARN": "arn",
            "SOLUTION_VERSION": "v9.9.9",
            "TRACE": "True",
            "USER_AGENT_EXTRA": "my-agent-extra",
            "ENABLE_AWS_ORGANIZATIONS": "False",
            "CONFIG_TABLE": "config-table-name",
        },
    ):
        with patch.object(main, "handlers", (mock_handler,)):
            assert lambda_handler({}, LambdaContext()) == my_response

    mock_handler.return_value.handle_request.assert_called_once()
