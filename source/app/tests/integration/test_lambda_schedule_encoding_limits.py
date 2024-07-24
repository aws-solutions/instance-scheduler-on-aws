# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
tests for schedule encoding limits of lambda

by default, all configured schedules are encoded into the event sent to the scheduling_request handler. However,
if a customer has too many schedules this event can exceed the maximum payload size for a Lambda request.

In this scenario the schedules will be omitted from the event, and instead need to be refetched from dynamodb
"""
import json
from typing import Iterator
from unittest.mock import MagicMock, patch

from _pytest.fixtures import fixture

from instance_scheduler.configuration.scheduling_context import SchedulingContext
from instance_scheduler.handler import scheduling_orchestrator
from instance_scheduler.handler.scheduling_orchestrator import (
    OrchestrationRequest,
    SchedulingOrchestratorHandler,
)
from instance_scheduler.handler.scheduling_request import (
    SchedulingRequest,
    SchedulingRequestHandler,
    validate_scheduler_request,
)
from instance_scheduler.model.period_definition import PeriodDefinition
from instance_scheduler.model.period_identifier import PeriodIdentifier
from instance_scheduler.model.schedule_definition import ScheduleDefinition
from instance_scheduler.model.store.ddb_config_item_store import DdbConfigItemStore
from instance_scheduler.model.store.in_memory_period_definition_store import (
    InMemoryPeriodDefinitionStore,
)
from instance_scheduler.model.store.in_memory_schedule_definition_store import (
    InMemoryScheduleDefinitionStore,
)
from instance_scheduler.model.store.period_definition_store import PeriodDefinitionStore
from instance_scheduler.model.store.schedule_definition_store import (
    ScheduleDefinitionStore,
)
from tests.context import MockLambdaContext
from tests.handler.test_scheduling_orchestration_handler import (
    scheduling_request_from_lambda_invoke,
)
from tests.integration.helpers.schedule_helpers import quick_time
from tests.logger import MockLogger
from tests.test_utils.mock_orchestrator_environment import MockOrchestratorEnvironment
from tests.test_utils.mock_scheduling_request_environment import (
    MockSchedulingRequestEnvironment,
)

mock_event_bridge_event: OrchestrationRequest = {
    "scheduled_action": "run_orchestrator",
}


@fixture
def mocked_lambda_invoke() -> Iterator[MagicMock]:
    with patch.object(SchedulingOrchestratorHandler, "lambda_client") as lambda_client:
        with patch.object(lambda_client, "invoke") as invoke_func:
            yield invoke_func


def test_schedules_and_periods_are_encoded_into_payload(
    mocked_lambda_invoke: MagicMock,
    schedule_store: ScheduleDefinitionStore,
    period_store: PeriodDefinitionStore,
    config_item_store: DdbConfigItemStore,
) -> None:
    schedule_store.put(
        ScheduleDefinition(
            name="my_schedule", periods=[PeriodIdentifier.of("my_period")]
        )
    )
    period_store.put(
        PeriodDefinition(
            name="my_period",
            begintime="10:00",
            endtime="20:00",
            monthdays={"1"},  # sets can cause json to fail if not handled correctly
            weekdays={"mon"},
            months={"jan"},
        )
    )

    SchedulingOrchestratorHandler(
        event=mock_event_bridge_event,
        context=MockLambdaContext(),
        env=MockOrchestratorEnvironment(
            schedule_regions=[],
            enable_ec2_service=True,
            enable_schedule_hub_account=True,
        ),
        logger=MockLogger(),
    ).handle_request()

    assert mocked_lambda_invoke.call_count == 1
    scheduling_request: SchedulingRequest = scheduling_request_from_lambda_invoke(
        mocked_lambda_invoke.call_args
    )

    assert "schedules" in scheduling_request
    assert "periods" in scheduling_request

    # validate expected serial data
    InMemoryScheduleDefinitionStore.validate_serial_data(
        scheduling_request["schedules"]
    )
    InMemoryPeriodDefinitionStore.validate_serial_data(scheduling_request["periods"])

    encoded_schedules = InMemoryScheduleDefinitionStore.deserialize(
        scheduling_request["schedules"]
    )
    encoded_periods = InMemoryPeriodDefinitionStore.deserialize(
        scheduling_request["periods"]
    )

    assert schedule_store.find_all() == encoded_schedules.find_all()
    assert period_store.find_all() == encoded_periods.find_all()


@patch.object(SchedulingOrchestratorHandler, "lambda_client")
def test_strips_schedules_when_payload_is_too_large(
    lambda_client: MagicMock, config_item_store: DdbConfigItemStore
) -> None:
    scheduling_orchestrator.LAMBDA_PAYLOAD_CAPACITY_BYTES = 0
    with patch.object(lambda_client, "invoke") as invoke_func:
        cloudwatch_handler = SchedulingOrchestratorHandler(
            event=mock_event_bridge_event,
            context=MockLambdaContext(),
            env=MockOrchestratorEnvironment(
                schedule_regions=[],
                enable_ec2_service=True,
                enable_schedule_hub_account=True,
            ),
            logger=MockLogger(),
        )
        cloudwatch_handler.handle_request()

        assert invoke_func.call_count == 1
        payload = invoke_func.call_args[1]["Payload"]

        scheduling_request: SchedulingRequest = json.loads(payload)
        validate_scheduler_request(scheduling_request)
        assert "schedules" not in scheduling_request
        assert "periods" not in scheduling_request


@patch("instance_scheduler.handler.scheduling_request.InstanceScheduler")
def test_scheduling_request_handler_reloads_schedules_when_not_provided(
    mock_scheduler: MagicMock,
    schedule_store: ScheduleDefinitionStore,
    period_store: PeriodDefinitionStore,
) -> None:
    # setup
    schedule_store.put(
        ScheduleDefinition(
            name="fetched_schedule", periods=[PeriodIdentifier.of("my_period")]
        )
    )

    period_store.put(PeriodDefinition(name="my_period", begintime="10:00"))

    request = SchedulingRequest(
        action="scheduler:run",
        account="123456789012",
        region="us-east-1",
        service="ec2",
        current_dt=quick_time(10, 0, 0).isoformat(),
        # schedules explicitly omitted,
        # periods explicitly omitted,
        dispatch_time=quick_time(10, 0, 0).isoformat(),
    )

    # run handler
    scheduling_handler = SchedulingRequestHandler(
        request, MockLambdaContext(), MockSchedulingRequestEnvironment(), MockLogger()
    )
    scheduling_handler.handle_request()

    # assert that when the schedules are not provided in the request they are still loaded from dynamo
    assert mock_scheduler.call_count == 1
    context_passed_to_scheduler: SchedulingContext = mock_scheduler.call_args.args[1]
    assert context_passed_to_scheduler.get_schedule("fetched_schedule") is not None
