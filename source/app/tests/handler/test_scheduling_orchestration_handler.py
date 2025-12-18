# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import json
from typing import TYPE_CHECKING, Any, Iterator
from unittest.mock import MagicMock, patch

import boto3
from _pytest.fixtures import fixture
from instance_scheduler.handler.scheduling_orchestrator import (
    OrchestrationRequest,
    SchedulingOrchestratorHandler,
    prefetch_schedules_and_periods,
)
from instance_scheduler.handler.scheduling_request import SchedulingRequest
from instance_scheduler.model.managed_instance import RegisteredEc2Instance
from instance_scheduler.model.period_definition import PeriodDefinition
from instance_scheduler.model.period_identifier import PeriodIdentifier
from instance_scheduler.model.schedule_definition import ScheduleDefinition
from instance_scheduler.model.store.period_definition_store import PeriodDefinitionStore
from instance_scheduler.model.store.resource_registry import ResourceRegistry
from instance_scheduler.model.store.schedule_definition_store import (
    ScheduleDefinitionStore,
)
from instance_scheduler.scheduling.states import InstanceState
from instance_scheduler.util.arn import ARN
from tests.context import MockLambdaContext
from tests.logger import MockLogger
from tests.test_utils.mock_orchestrator_environment import MockOrchestratorEnvironment

if TYPE_CHECKING:
    from mypy_boto3_dynamodb.client import DynamoDBClient
else:
    DynamoDBClient = object

mockEvent: OrchestrationRequest = {"scheduled_action": "run_orchestrator"}


@fixture
def mocked_lambda_invoke() -> Iterator[MagicMock]:
    with patch.object(SchedulingOrchestratorHandler, "lambda_client") as lambda_client:
        with patch.object(lambda_client, "invoke") as invoke_func:
            yield invoke_func


def scheduling_request_from_lambda_invoke(call_args: Any) -> SchedulingRequest:
    payload = call_args.kwargs["Payload"]
    scheduling_request: SchedulingRequest = json.loads(payload)
    return scheduling_request


def test_prefetch_gracefully_handles_invalid_configurations(
    config_table: str,
    period_store: PeriodDefinitionStore,
    schedule_store: ScheduleDefinitionStore,
) -> None:
    # Add valid period and schedule
    period_store.put(
        PeriodDefinition(name="valid-period", begintime="09:00", endtime="17:00")
    )
    schedule_store.put(
        ScheduleDefinition(
            name="valid-schedule", periods=[PeriodIdentifier("valid-period")]
        )
    )

    # Add invalid period via direct DDB insert
    ddb_client: DynamoDBClient = boto3.client("dynamodb")
    ddb_client.put_item(
        TableName=config_table,
        Item={
            "type": {"S": "period"},
            "name": {"S": "invalid-period"},
            "begintime": {"S": "20:00"},  # begintime after endtime
            "endtime": {"S": "15:00"},
        },
    )

    schedule_store.put(
        ScheduleDefinition(
            name="schedule-with-missing-periods", periods=[PeriodIdentifier("unknown")]
        )
    )

    schedules, periods = prefetch_schedules_and_periods(
        MockOrchestratorEnvironment(), MockLogger()
    )
    # Should have 1 valid schedule and 1 valid period, invalid ones filtered out
    assert len(periods.find_all()) == 1
    assert len(schedules.find_all()) == 1
    assert "valid-schedule" in schedules.find_all()
    assert "valid-period" in periods.find_all()


# ##------------------- FAN OUT BEHAVIOR -----------------## #
def test_no_scheduling_targets(
    mocked_lambda_invoke: MagicMock,
    resource_registry: ResourceRegistry,
    registry_table: str,
    config_table: str,
) -> None:
    orchestrator = SchedulingOrchestratorHandler(
        event=mockEvent,
        context=MockLambdaContext(),
        env=MockOrchestratorEnvironment(registry_table=registry_table),
        logger=MockLogger(),
    )
    orchestrator.handle_request()
    assert mocked_lambda_invoke.call_count == 0


def test_single_scheduling_target(
    mocked_lambda_invoke: MagicMock,
    resource_registry: ResourceRegistry,
    schedule_store: ScheduleDefinitionStore,
    period_store: PeriodDefinitionStore,
    registry_table: str,
) -> None:
    period_store.put(
        PeriodDefinition(name="test-period", begintime="09:00", endtime="17:00")
    )
    schedule_store.put(
        ScheduleDefinition(
            name="test-schedule", periods=[PeriodIdentifier("test-period")]
        )
    )

    resource_registry.put(
        RegisteredEc2Instance(
            account="111111111111",
            region="us-east-1",
            resource_id="i-1",
            arn=ARN("arn:aws:ec2:us-east-1:111111111111:instance/i-1"),
            schedule="test-schedule",
            name="test-instance",
            stored_state=InstanceState.RUNNING,
        )
    )

    orchestrator = SchedulingOrchestratorHandler(
        event=mockEvent,
        context=MockLambdaContext(),
        env=MockOrchestratorEnvironment(registry_table=registry_table),
        logger=MockLogger(),
    )
    orchestrator.handle_request()

    assert mocked_lambda_invoke.call_count == 1

    scheduling_request: SchedulingRequest = scheduling_request_from_lambda_invoke(
        mocked_lambda_invoke.call_args
    )
    assert scheduling_request["account"] == "111111111111"
    assert scheduling_request["region"] == "us-east-1"
    assert scheduling_request["service"] == "ec2"
    schedules = scheduling_request["schedules"]
    periods = scheduling_request["periods"]
    assert any(s["name"] == "test-schedule" for s in schedules)
    assert any(p["name"] == "test-period" for p in periods)


def test_multiple_scheduling_targets(
    mocked_lambda_invoke: MagicMock,
    resource_registry: ResourceRegistry,
    schedule_store: ScheduleDefinitionStore,
    period_store: PeriodDefinitionStore,
    registry_table: str,
) -> None:
    period_store.put(
        PeriodDefinition(name="period1", begintime="09:00", endtime="17:00")
    )
    period_store.put(
        PeriodDefinition(name="period2", begintime="18:00", endtime="22:00")
    )
    schedule_store.put(
        ScheduleDefinition(name="schedule1", periods=[PeriodIdentifier("period1")])
    )
    schedule_store.put(
        ScheduleDefinition(name="schedule2", periods=[PeriodIdentifier("period2")])
    )

    resource_registry.put(
        RegisteredEc2Instance(
            account="111111111111",
            region="us-east-1",
            resource_id="i-1",
            arn=ARN("arn:aws:ec2:us-east-1:111111111111:instance/i-1"),
            schedule="schedule1",
            name="instance1",
            stored_state=InstanceState.RUNNING,
        )
    )
    resource_registry.put(
        RegisteredEc2Instance(
            account="222222222222",
            region="us-west-2",
            resource_id="i-2",
            arn=ARN("arn:aws:ec2:us-west-2:222222222222:instance/i-2"),
            schedule="schedule2",
            name="instance2",
            stored_state=InstanceState.RUNNING,
        )
    )

    orchestrator = SchedulingOrchestratorHandler(
        event=mockEvent,
        context=MockLambdaContext(),
        env=MockOrchestratorEnvironment(registry_table=registry_table),
        logger=MockLogger(),
    )
    orchestrator.handle_request()

    assert mocked_lambda_invoke.call_count == 2

    requests = [
        scheduling_request_from_lambda_invoke(call)
        for call in mocked_lambda_invoke.call_args_list
    ]
    targets = [(r["account"], r["region"], r["service"]) for r in requests]

    assert ("111111111111", "us-east-1", "ec2") in targets
    assert ("222222222222", "us-west-2", "ec2") in targets

    # Verify schedules are properly encoded for each target
    for request in requests:
        schedules = request["schedules"]
        periods = request["periods"]
        if request["account"] == "111111111111":
            assert any(s["name"] == "schedule1" for s in schedules)
            assert any(p["name"] == "period1" for p in periods)
        elif request["account"] == "222222222222":
            assert any(s["name"] == "schedule2" for s in schedules)
            assert any(p["name"] == "period2" for p in periods)
