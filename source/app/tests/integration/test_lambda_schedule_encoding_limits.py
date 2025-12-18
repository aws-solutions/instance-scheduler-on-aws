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
from instance_scheduler.handler import scheduling_orchestrator
from instance_scheduler.handler.scheduling_orchestrator import (
    OrchestrationRequest,
    SchedulingOrchestratorHandler,
)
from instance_scheduler.handler.scheduling_request import (
    SchedulingRequest,
    validate_scheduler_request,
)
from instance_scheduler.model.managed_instance import RegisteredEc2Instance
from instance_scheduler.model.period_definition import PeriodDefinition
from instance_scheduler.model.period_identifier import PeriodIdentifier
from instance_scheduler.model.schedule_definition import ScheduleDefinition
from instance_scheduler.model.store.in_memory_period_definition_store import (
    InMemoryPeriodDefinitionStore,
)
from instance_scheduler.model.store.in_memory_schedule_definition_store import (
    InMemoryScheduleDefinitionStore,
)
from instance_scheduler.model.store.period_definition_store import PeriodDefinitionStore
from instance_scheduler.model.store.resource_registry import ResourceRegistry
from instance_scheduler.model.store.schedule_definition_store import (
    ScheduleDefinitionStore,
)
from instance_scheduler.scheduling.states import InstanceState
from instance_scheduler.util.arn import ARN
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
    resource_registry: ResourceRegistry,
    schedule_store: ScheduleDefinitionStore,
    period_store: PeriodDefinitionStore,
    registry_table: str,
) -> None:
    schedule_store.put(
        ScheduleDefinition(
            name="my_schedule", periods=[PeriodIdentifier.of("my_period")]
        )
    )
    schedule_store.put(
        ScheduleDefinition(
            name="unused_schedule", periods=[PeriodIdentifier.of("unused_period")]
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
    period_store.put(
        PeriodDefinition(
            name="unused_period",
            begintime="22:00",
            endtime="23:00",
        )
    )

    resource_registry.put(
        RegisteredEc2Instance(
            account="123456789012",
            region="us-east-1",
            resource_id="i-1",
            arn=ARN("arn:aws:ec2:us-east-1:123456789012:instance/i-1"),
            schedule="my_schedule",
            name="test-instance",
            stored_state=InstanceState.RUNNING,
        )
    )

    SchedulingOrchestratorHandler(
        event=mock_event_bridge_event,
        context=MockLambdaContext(),
        env=MockOrchestratorEnvironment(registry_table=registry_table),
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

    # Only the schedule used by registered instances should be encoded
    assert "my_schedule" in encoded_schedules.find_all()
    assert "my_period" in encoded_periods.find_all()
    # Unused schedules/periods should NOT be encoded
    assert "unused_schedule" not in encoded_schedules.find_all()
    assert "unused_period" not in encoded_periods.find_all()


@patch.object(SchedulingOrchestratorHandler, "lambda_client")
def test_strips_schedules_when_payload_is_too_large(
    lambda_client: MagicMock,
    resource_registry: ResourceRegistry,
    schedule_store: ScheduleDefinitionStore,
    period_store: PeriodDefinitionStore,
    registry_table: str,
) -> None:
    schedule_store.put(
        ScheduleDefinition(
            name="test-schedule", periods=[PeriodIdentifier("test-period")]
        )
    )
    period_store.put(
        PeriodDefinition(name="test-period", begintime="09:00", endtime="17:00")
    )

    resource_registry.put(
        RegisteredEc2Instance(
            account="123456789012",
            region="us-east-1",
            resource_id="i-1",
            arn=ARN("arn:aws:ec2:us-east-1:123456789012:instance/i-1"),
            schedule="test-schedule",
            name="test-instance",
            stored_state=InstanceState.RUNNING,
        )
    )

    scheduling_orchestrator.LAMBDA_PAYLOAD_CAPACITY_BYTES = 0
    with patch.object(lambda_client, "invoke") as invoke_func:
        cloudwatch_handler = SchedulingOrchestratorHandler(
            event=mock_event_bridge_event,
            context=MockLambdaContext(),
            env=MockOrchestratorEnvironment(registry_table=registry_table),
            logger=MockLogger(),
        )
        cloudwatch_handler.handle_request()

        assert invoke_func.call_count == 1
        payload = invoke_func.call_args[1]["Payload"]

        scheduling_request: SchedulingRequest = json.loads(payload)
        validate_scheduler_request(scheduling_request)
        assert "schedules" not in scheduling_request
        assert "periods" not in scheduling_request


def test_scheduling_request_handler_reloads_schedules_when_not_provided(
    schedule_store: ScheduleDefinitionStore,
    period_store: PeriodDefinitionStore,
) -> None:
    from instance_scheduler.handler.scheduling_request import build_scheduling_context

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

    # Test build_scheduling_context directly
    with MockSchedulingRequestEnvironment().patch_env():
        context = build_scheduling_context(request, MockSchedulingRequestEnvironment())

    # Verify the schedule was loaded from DynamoDB into the cached store
    fetched_schedule = context.schedule_store.find_by_name("fetched_schedule")
    assert fetched_schedule is not None
    assert fetched_schedule.name == "fetched_schedule"
    assert fetched_schedule is not None
    assert fetched_schedule.name == "fetched_schedule"
