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
from instance_scheduler.model.ddb_config_item import DdbConfigItem
from instance_scheduler.model.period_identifier import PeriodIdentifier
from instance_scheduler.model.schedule_definition import ScheduleDefinition
from instance_scheduler.model.store.ddb_config_item_store import DdbConfigItemStore
from instance_scheduler.model.store.dynamo_period_definition_store import (
    DynamoPeriodDefinitionStore,
)
from instance_scheduler.model.store.dynamo_schedule_definition_store import (
    DynamoScheduleDefinitionStore,
)
from tests.context import MockLambdaContext
from tests.logger import MockLogger
from tests.test_utils.mock_orchestrator_environment import MockOrchestratorEnvironment

if TYPE_CHECKING:
    from mypy_boto3_dynamodb.client import DynamoDBClient
    from mypy_boto3_ssm.client import SSMClient
else:
    SSMClient = object
    DynamoDBClient = object

mockEvent: OrchestrationRequest = {"scheduled_action": "run_orchestrator"}
moto_hub_account = "123456789012"


def orchestrator_env_overrides(
    schedule_regions: list[str] = [],
    enable_ec2_service: bool = False,
    enable_rds_service: bool = False,
    enable_rds_clusters: bool = False,
    enable_neptune_service: bool = False,
    enable_docdb_service: bool = False,
    enable_schedule_hub_account: bool = False,
) -> dict[str, Any]:
    return {
        "schedule_regions": schedule_regions,
        "enable_ec2_service": enable_ec2_service,
        "enable_rds_service": enable_rds_service,
        "enable_rds_clusters": enable_rds_clusters,
        "enable_neptune_service": enable_neptune_service,
        "enable_docdb_service": enable_docdb_service,
        "enable_schedule_hub_account": enable_schedule_hub_account,
    }


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
    period_store: DynamoPeriodDefinitionStore,
    schedule_store: DynamoScheduleDefinitionStore,
) -> None:
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
    assert len(periods.find_all()) == 0
    assert len(schedules.find_all()) == 0
    # todo: write assertions against the errors that get logged to sns (see output to MockLogger)


# ##------------------- FAN OUT BEHAVIOR -----------------## #
def test_no_region_provided_uses_local_region(
    mocked_lambda_invoke: MagicMock,
    config_item_store: DdbConfigItemStore,
) -> None:
    orchestrator = SchedulingOrchestratorHandler(
        event=mockEvent,
        context=MockLambdaContext(),
        env=MockOrchestratorEnvironment(
            schedule_regions=[],
            enable_ec2_service=True,
            enable_schedule_hub_account=True,
        ),
        logger=MockLogger(),
    )
    orchestrator.handle_request()
    assert mocked_lambda_invoke.call_count == 1
    scheduling_request: SchedulingRequest = scheduling_request_from_lambda_invoke(
        mocked_lambda_invoke.call_args
    )
    assert scheduling_request["account"] == moto_hub_account
    assert scheduling_request["service"] == "ec2"
    assert scheduling_request["region"] == "us-east-1"


def test_no_service_provided_does_not_run_any_lambdas(
    mocked_lambda_invoke: MagicMock,
    config_item_store: DdbConfigItemStore,
) -> None:
    orchestrator = SchedulingOrchestratorHandler(
        event=mockEvent,
        context=MockLambdaContext(),
        env=MockOrchestratorEnvironment(
            schedule_regions=["us-east-1"], enable_schedule_hub_account=True
        ),
        logger=MockLogger(),
    )
    orchestrator.handle_request()

    assert mocked_lambda_invoke.call_count == 0


def test_remote_account_only_does_not_schedule_locally(
    mocked_lambda_invoke: MagicMock,
    config_item_store: DdbConfigItemStore,
) -> None:
    config_item_store.put(
        DdbConfigItem(organization_id="", remote_account_ids=["222233334444"])
    )

    orchestrator = SchedulingOrchestratorHandler(
        event=mockEvent,
        context=MockLambdaContext(),
        env=MockOrchestratorEnvironment(
            schedule_regions=["us-east-1"],
            enable_ec2_service=True,
            enable_schedule_hub_account=False,
        ),
        logger=MockLogger(),
    )
    orchestrator.handle_request()

    assert mocked_lambda_invoke.call_count == 1

    scheduling_request: SchedulingRequest = scheduling_request_from_lambda_invoke(
        mocked_lambda_invoke.call_args
    )
    assert scheduling_request["service"] == "ec2"
    assert scheduling_request["account"] == "222233334444"
    assert scheduling_request["region"] == "us-east-1"


def test_1region_1service_calls_scheduler_x1(
    mocked_lambda_invoke: MagicMock,
    config_item_store: DdbConfigItemStore,
) -> None:
    orchestrator = SchedulingOrchestratorHandler(
        event=mockEvent,
        context=MockLambdaContext(),
        env=MockOrchestratorEnvironment(
            schedule_regions=["us-east-1"],
            enable_ec2_service=True,
            enable_schedule_hub_account=True,
        ),
        logger=MockLogger(),
    )
    orchestrator.handle_request()

    assert mocked_lambda_invoke.call_count == 1

    scheduling_request: SchedulingRequest = scheduling_request_from_lambda_invoke(
        mocked_lambda_invoke.call_args
    )
    assert scheduling_request["account"] == moto_hub_account
    assert scheduling_request["region"] == "us-east-1"
    assert scheduling_request["service"] == "ec2"


def test_2region_1service_calls_scheduler_x2(
    mocked_lambda_invoke: MagicMock,
    config_item_store: DdbConfigItemStore,
) -> None:
    orchestrator = SchedulingOrchestratorHandler(
        event=mockEvent,
        context=MockLambdaContext(),
        env=MockOrchestratorEnvironment(
            schedule_regions=["us-east-1", "us-east-2"],
            enable_ec2_service=True,
            enable_schedule_hub_account=True,
        ),
        logger=MockLogger(),
    )
    orchestrator.handle_request()

    assert mocked_lambda_invoke.call_count == 2

    # first call
    scheduling_request: SchedulingRequest = scheduling_request_from_lambda_invoke(
        mocked_lambda_invoke.call_args_list[0]
    )

    assert scheduling_request["account"] == moto_hub_account
    assert scheduling_request["region"] == "us-east-1"
    assert scheduling_request["service"] == "ec2"

    # second call
    scheduling_request = scheduling_request_from_lambda_invoke(
        mocked_lambda_invoke.call_args_list[1]
    )
    assert scheduling_request["account"] == moto_hub_account
    assert scheduling_request["region"] == "us-east-2"
    assert scheduling_request["service"] == "ec2"


def test_2accounts_1region_1service_nolocal_calls_scheduler_twice(
    mocked_lambda_invoke: MagicMock,
    config_item_store: DdbConfigItemStore,
) -> None:
    config_item_store.put(
        DdbConfigItem(
            organization_id="", remote_account_ids=["222233334444", "333344445555"]
        )
    )

    orchestrator = SchedulingOrchestratorHandler(
        event=mockEvent,
        context=MockLambdaContext(),
        env=MockOrchestratorEnvironment(
            schedule_regions=["us-east-1"],
            enable_ec2_service=True,
            enable_schedule_hub_account=False,
        ),
        logger=MockLogger(),
    )
    orchestrator.handle_request()

    assert mocked_lambda_invoke.call_count == 2

    # first call
    scheduling_request: SchedulingRequest = scheduling_request_from_lambda_invoke(
        mocked_lambda_invoke.call_args_list[0]
    )
    assert scheduling_request["region"] == "us-east-1"
    assert scheduling_request["service"] == "ec2"
    assert scheduling_request["account"] == "222233334444"

    # second call
    scheduling_request = scheduling_request_from_lambda_invoke(
        mocked_lambda_invoke.call_args_list[1]
    )
    assert scheduling_request["region"] == "us-east-1"
    assert scheduling_request["service"] == "ec2"
    assert scheduling_request["account"] == "333344445555"


def test_2accounts_1region_1service_with_local_calls_scheduler_x3(
    mocked_lambda_invoke: MagicMock,
    config_item_store: DdbConfigItemStore,
) -> None:
    config_item_store.put(
        DdbConfigItem(
            organization_id="", remote_account_ids=["222233334444", "333344445555"]
        )
    )

    orchestrator = SchedulingOrchestratorHandler(
        event=mockEvent,
        context=MockLambdaContext(),
        env=MockOrchestratorEnvironment(
            schedule_regions=["us-east-1"],
            enable_ec2_service=True,
            enable_schedule_hub_account=True,
        ),
        logger=MockLogger(),
    )
    orchestrator.handle_request()

    assert mocked_lambda_invoke.call_count == 3

    # first call
    scheduling_request: SchedulingRequest = scheduling_request_from_lambda_invoke(
        mocked_lambda_invoke.call_args_list[0]
    )
    assert scheduling_request["region"] == "us-east-1"
    assert scheduling_request["service"] == "ec2"
    assert scheduling_request["account"] == moto_hub_account

    # second call
    scheduling_request = scheduling_request_from_lambda_invoke(
        mocked_lambda_invoke.call_args_list[1]
    )
    assert scheduling_request["region"] == "us-east-1"
    assert scheduling_request["service"] == "ec2"
    assert scheduling_request["account"] == "222233334444"

    # third call
    scheduling_request = scheduling_request_from_lambda_invoke(
        mocked_lambda_invoke.call_args_list[2]
    )
    assert scheduling_request["region"] == "us-east-1"
    assert scheduling_request["service"] == "ec2"
    assert scheduling_request["account"] == "333344445555"


def test_1region_2service_calls_scheduler_x2(
    mocked_lambda_invoke: MagicMock,
    config_item_store: DdbConfigItemStore,
) -> None:
    orchestrator = SchedulingOrchestratorHandler(
        event=mockEvent,
        context=MockLambdaContext(),
        env=MockOrchestratorEnvironment(
            schedule_regions=["us-east-1"],
            enable_ec2_service=True,
            enable_rds_service=True,
            enable_schedule_hub_account=True,
        ),
        logger=MockLogger(),
    )
    orchestrator.handle_request()

    assert mocked_lambda_invoke.call_count == 2

    # first call
    scheduling_request: SchedulingRequest = scheduling_request_from_lambda_invoke(
        mocked_lambda_invoke.call_args_list[0]
    )
    assert scheduling_request["region"] == "us-east-1"
    assert scheduling_request["service"] == "ec2"

    # second call
    scheduling_request = scheduling_request_from_lambda_invoke(
        mocked_lambda_invoke.call_args_list[1]
    )
    assert scheduling_request["region"] == "us-east-1"
    assert scheduling_request["service"] == "rds"


def test_3account_3region_2service_calls_scheduler_x18(
    mocked_lambda_invoke: MagicMock,
    config_item_store: DdbConfigItemStore,
) -> None:
    config_item_store.put(
        DdbConfigItem(
            organization_id="",
            remote_account_ids=["111122223333", "222233334444", "333344445555"],
        )
    )

    orchestrator = SchedulingOrchestratorHandler(
        event=mockEvent,
        context=MockLambdaContext(),
        env=MockOrchestratorEnvironment(
            schedule_regions=["us-east-1", "us-east-2", "us-west-1"],
            enable_ec2_service=True,
            enable_rds_service=True,
            enable_schedule_hub_account=False,
        ),
        logger=MockLogger(),
    )
    orchestrator.handle_request()

    assert mocked_lambda_invoke.call_count == 18
    for index, call in enumerate(mocked_lambda_invoke.call_args_list):
        scheduling_request: SchedulingRequest = scheduling_request_from_lambda_invoke(
            call
        )
        assert scheduling_request["region"]  # assert exists
        assert scheduling_request["account"]
        assert scheduling_request["service"]


# ##------------------- SSM Parameter Resolution -----------------## #
def test_ssm_parameter_string_list_is_resolved_to_account_ids(
    mocked_lambda_invoke: MagicMock,
    config_item_store: DdbConfigItemStore,
) -> None:
    ssm_client: SSMClient = boto3.client("ssm")
    ssm_client.put_parameter(
        Name="my_ssm_param", Value="555566667777,666677778888", Type="StringList"
    )

    config_item_store.put(
        DdbConfigItem(
            organization_id="",
            remote_account_ids=["{param:my_ssm_param}", "111122223333"],
        )
    )

    orchestrator = SchedulingOrchestratorHandler(
        event=mockEvent,
        context=MockLambdaContext(),
        env=MockOrchestratorEnvironment(
            schedule_regions=["us-east-1"],
            enable_ec2_service=True,
            enable_schedule_hub_account=False,
        ),
        logger=MockLogger(),
    )
    orchestrator.handle_request()

    # first call
    scheduling_request: SchedulingRequest = scheduling_request_from_lambda_invoke(
        mocked_lambda_invoke.call_args_list[0]
    )
    assert scheduling_request["account"] == "555566667777"
    assert scheduling_request["region"] == "us-east-1"
    assert scheduling_request["service"] == "ec2"

    # second call
    scheduling_request = scheduling_request_from_lambda_invoke(
        mocked_lambda_invoke.call_args_list[1]
    )
    assert scheduling_request["account"] == "666677778888"
    assert scheduling_request["region"] == "us-east-1"
    assert scheduling_request["service"] == "ec2"

    # third call
    scheduling_request = scheduling_request_from_lambda_invoke(
        mocked_lambda_invoke.call_args_list[2]
    )
    assert scheduling_request["account"] == "111122223333"
    assert scheduling_request["region"] == "us-east-1"
    assert scheduling_request["service"] == "ec2"


def test_ssm_parameter_string_is_resolved_to_account_id(
    mocked_lambda_invoke: MagicMock,
    config_item_store: DdbConfigItemStore,
) -> None:
    ssm_client: SSMClient = boto3.client("ssm")
    ssm_client.put_parameter(Name="my_ssm_param", Value="555566667777", Type="String")

    config_item_store.put(
        DdbConfigItem(
            organization_id="",
            remote_account_ids=["{param:my_ssm_param}"],
        )
    )

    orchestrator = SchedulingOrchestratorHandler(
        event=mockEvent,
        context=MockLambdaContext(),
        env=MockOrchestratorEnvironment(
            schedule_regions=["us-east-1"],
            enable_ec2_service=True,
            enable_schedule_hub_account=False,
        ),
        logger=MockLogger(),
    )
    orchestrator.handle_request()

    assert mocked_lambda_invoke.call_count == 1

    scheduling_request: SchedulingRequest = scheduling_request_from_lambda_invoke(
        mocked_lambda_invoke.call_args
    )
    assert scheduling_request["service"] == "ec2"
    assert scheduling_request["account"] == "555566667777"
    assert scheduling_request["region"] == "us-east-1"
