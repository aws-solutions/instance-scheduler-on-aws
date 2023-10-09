# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from unittest.mock import MagicMock, patch

from aws_lambda_powertools.utilities.typing import LambdaContext

from instance_scheduler import main
from instance_scheduler.handler.scheduling_orchestrator import (
    OrchestrationRequest,
    SchedulingOrchestratorHandler,
)
from instance_scheduler.main import lambda_handler
from instance_scheduler.util.logger import Logger
from tests.context import MockLambdaContext


def test_scheduling_request_handler_called() -> None:
    mock_handler = MagicMock()
    mock_handler.is_handling_request.return_value = True
    my_response = "Everything's great!"
    mock_handler.return_value.handle_request.return_value = my_response
    mock_handler.__name__ = "my-handler"

    with patch.object(main, "handlers", (mock_handler,)):
        assert lambda_handler({}, LambdaContext()) == my_response

    mock_handler.return_value.handle_request.assert_called_once()


@patch.object(Logger, "client")
@patch.object(SchedulingOrchestratorHandler, "handle_request")
def test_orchestrator_event(
    handle_request_method: MagicMock, logger_client: MagicMock
) -> None:
    event: OrchestrationRequest = {
        "scheduled_action": "run_orchestrator",
    }

    lambda_handler(event, MockLambdaContext())
    handle_request_method.assert_called_once()
