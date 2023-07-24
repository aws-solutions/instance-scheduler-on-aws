# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import json
from datetime import datetime
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

from freezegun import freeze_time

from instance_scheduler.handler.scheduling_orchestrator import (
    OrchestrationRequest,
    SchedulingOrchestratorHandler,
)
from instance_scheduler.util.app_env import AppEnv
from tests.context import MockLambdaContext
from tests.integration.ops_metrics.conftest import solution_metrics_uuid
from tests.util.test_global_config import sample_global_config

mockEvent: OrchestrationRequest = {"scheduled_action": "run_orchestrator"}


@patch.object(SchedulingOrchestratorHandler, "_run_scheduling_lambda")
@freeze_time(datetime(2023, 6, 12, 12, 0, 0, tzinfo=ZoneInfo("UTC")))
def test_orchestrator_sends_expected_metric(
    run_lambda_func: MagicMock, mock_metrics_endpoint: MagicMock, app_env: AppEnv
) -> None:
    global_config = sample_global_config()
    global_config.regions = ["us-east-1", "us-east-2", "us-west-2"]
    global_config.scheduled_services = ["ec2", "rds"]
    global_config.remote_account_ids = ["222233334444", "333344445555"]
    global_config.schedule_lambda_account = True

    with patch.object(SchedulingOrchestratorHandler, "configuration", global_config):
        handler = SchedulingOrchestratorHandler(
            event=mockEvent, context=MockLambdaContext()
        )
        handler.handle_request()

        expected_metric = {
            "TimeStamp": "2023-06-12 12:00:00",
            "UUID": str(solution_metrics_uuid),
            "Solution": app_env.solution_id,
            "Version": app_env.solution_version,
            "Event_Name": "deployment_description",
            "Context": {
                "services": ["ec2", "rds"],
                "regions": ["us-east-1", "us-east-2", "us-west-2"],
                "num_accounts": 3,  # local account + 2 remote
            },
        }

        assert mock_metrics_endpoint.call_count == 1
        json_payload = mock_metrics_endpoint.call_args[1]["data"]
        assert json.loads(json_payload) == expected_metric
