# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import datetime
import json
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

from freezegun.api import freeze_time

from instance_scheduler import __version__
from instance_scheduler.handler.cli.cli_request_handler import CliRequestHandler
from tests.context import MockLambdaContext
from tests.logger import MockLogger
from tests.test_utils.mock_main_lambda_env import MockMainLambdaEnv
from tests.test_utils.mock_metrics_environment import MockMetricsEnviron


@freeze_time(datetime.datetime(2023, 6, 12, 12, 0, 0, tzinfo=ZoneInfo("UTC")))
def test_cli_handler_sends_expected_metric(mock_metrics_endpoint: MagicMock) -> None:
    with MockMetricsEnviron(send_anonymous_metrics=True) as metrics_environment:
        action = "my-action"
        parameters = {"my_key": "my-value"}
        handler = CliRequestHandler(
            {
                "action": action,
                "parameters": parameters,
                "version": __version__,
            },
            MockLambdaContext(),
            MockMainLambdaEnv(),
        )
        handler._logger = MockLogger()
        handler.handle_request()

        expected_metric = {
            "timestamp": "2023-06-12 12:00:00",
            "uuid": str(metrics_environment.metrics_uuid),
            "solution": metrics_environment.solution_id,
            "version": metrics_environment.solution_version,
            "event_name": "cli_request",
            "context_version": 1,
            "context": {"command_used": action},
        }

        assert mock_metrics_endpoint.call_count == 1
        json_payload = mock_metrics_endpoint.call_args[1]["body"]
        assert json.loads(json_payload) == expected_metric
