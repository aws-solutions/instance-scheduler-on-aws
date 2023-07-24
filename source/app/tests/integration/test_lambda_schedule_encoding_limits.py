# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
tests for schedule encoding limits of lambda

by default, all configured schedules are encoded into the event sent to the scheduling_request handler. However,
if a customer has too many schedules this event can exceed the maximum payload size for a Lambda request.

In this scenario the schedules will be omitted from the event, and instead need to be refetched from dynamodb
"""
import datetime
import json
from unittest.mock import MagicMock, patch

from instance_scheduler import configuration
from instance_scheduler.configuration.instance_schedule import InstanceSchedule
from instance_scheduler.configuration.running_period import RunningPeriod
from instance_scheduler.configuration.scheduling_context import SchedulingContext
from instance_scheduler.handler import scheduling_orchestrator
from instance_scheduler.handler.scheduling_orchestrator import (
    OrchestrationRequest,
    SchedulingOrchestratorHandler,
)
from instance_scheduler.handler.scheduling_request import (
    SchedulerRequest,
    SchedulingRequestHandler,
)
from tests.context import MockLambdaContext
from tests.integration.helpers.global_config import build_global_config
from tests.integration.helpers.schedule_helpers import quick_time
from tests.integration.helpers.scheduling_context_builder import build_context

global_config = build_global_config(
    schedules={
        "global-schedule": InstanceSchedule(
            name="global-schedule",
            periods=[
                {
                    "period": RunningPeriod(
                        name="global-period",
                        begintime=datetime.time(10, 0, 0),
                        endtime=datetime.time(20, 0, 0),
                    )
                }
            ],
        )
    },
)

mock_event_bridge_event: OrchestrationRequest = {
    "scheduled_action": "run_orchestrator",
}


def build_stripped_event(context: SchedulingContext) -> SchedulerRequest:
    payload = context.to_dict()
    scheduling_orchestrator.strip_schedules_and_periods(payload)
    return {
        "action": "scheduler:run",
        "configuration": payload,
        "dispatch_time": "dispatchTime",
    }


@patch.object(SchedulingOrchestratorHandler, "configuration", global_config)
@patch.object(SchedulingOrchestratorHandler, "lambda_client")
def test_strips_schedules_when_payload_is_too_large(lambda_client: MagicMock) -> None:
    scheduling_orchestrator.LAMBDA_PAYLOAD_CAPACITY_BYTES = 0
    with patch.object(lambda_client, "invoke") as invoke_func:
        cloudwatch_handler = SchedulingOrchestratorHandler(
            event=mock_event_bridge_event, context=MockLambdaContext()
        )
        cloudwatch_handler.handle_request()

        assert invoke_func.call_count == 1
        payload = invoke_func.call_args[1]["Payload"]
        content = json.loads(payload)
        assert content["configuration"]["schedules"] == {}
        assert content["configuration"]["periods"] == {}


@patch.object(configuration, "get_global_configuration")
@patch("instance_scheduler.handler.scheduling_request.InstanceScheduler")
def test_scheduling_request_handler_reloads_schedules_when_not_provided(
    mock_scheduler: MagicMock, fetch_global_config_func: MagicMock
) -> None:
    # setup
    fetch_global_config_func.return_value = global_config
    context = build_context(current_dt=quick_time(10, 0, 0))
    event = build_stripped_event(context)

    # run handler
    scheduling_handler = SchedulingRequestHandler(event, MockLambdaContext())
    scheduling_handler.handle_request()

    # assert that the schedule that gets passed to instance_scheduler is global-schedule, not stripped-schedule
    assert mock_scheduler.call_count == 1
    schedules_passed_to_scheduler = mock_scheduler.call_args.args[1].schedules
    assert "global-schedule" in schedules_passed_to_scheduler
    assert "stripped-schedule" not in schedules_passed_to_scheduler
