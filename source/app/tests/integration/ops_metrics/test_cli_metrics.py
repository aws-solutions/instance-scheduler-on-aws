# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import datetime
import json
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

from freezegun.api import freeze_time

from instance_scheduler.handler.cli import CliHandler
from instance_scheduler.util.app_env import AppEnv
from tests.context import MockLambdaContext
from tests.integration.ops_metrics.conftest import solution_metrics_uuid
from tests.logger import MockLogger


@freeze_time(datetime.datetime(2023, 6, 12, 12, 0, 0, tzinfo=ZoneInfo("UTC")))
def test_cli_handler_sends_expected_metric(
    mock_metrics_endpoint: MagicMock, app_env: AppEnv
) -> None:
    action = "my-action"
    parameters = {"my_key": "my-value"}
    handler = CliHandler(
        {"action": action, "parameters": parameters},
        MockLambdaContext(),
    )
    handler._logger = MockLogger()
    handler.handle_request()

    expected_metric = {
        "TimeStamp": "2023-06-12 12:00:00",
        "UUID": str(solution_metrics_uuid),
        "Solution": app_env.solution_id,
        "Version": app_env.solution_version,
        "Event_Name": "cli_request",
        "Context": {"command_used": action},
    }

    assert mock_metrics_endpoint.call_count == 1
    json_payload = mock_metrics_endpoint.call_args[1]["data"]
    assert json.loads(json_payload) == expected_metric
