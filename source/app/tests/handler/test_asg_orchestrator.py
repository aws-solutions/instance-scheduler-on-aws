# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import json
from collections.abc import Iterator
from datetime import datetime, timezone
from itertools import chain, product
from typing import TYPE_CHECKING, Final
from unittest.mock import MagicMock, patch

from boto3 import client
from boto3.session import Session
from freezegun import freeze_time
from moto.core.models import DEFAULT_ACCOUNT_ID
from pytest import fixture

from instance_scheduler.handler.asg_orchestrator import orchestrate_asgs
from instance_scheduler.handler.scheduling_request import SchedulingRequest
from instance_scheduler.model.ddb_config_item import DdbConfigItem
from instance_scheduler.model.store.ddb_config_item_store import DdbConfigItemStore
from tests.context import MockLambdaContext
from tests.test_utils.mock_asg_orchestrator_environment import (
    MockAsgOrchestratorEnvironment,
)

if TYPE_CHECKING:
    from mypy_boto3_ssm.client import SSMClient
else:
    SSMClient = object


@fixture
def remote_accounts(config_item_store: DdbConfigItemStore) -> Iterator[list[str]]:
    param_name: Final = "my_ssm_param"
    param_value: Final = "444444444444"
    ssm_client: Final[SSMClient] = client("ssm")
    ssm_client.put_parameter(Name=param_name, Value=param_value, Type="String")

    remote_account_ids: Final = [
        "222222222222",
        "333333333333",
    ]
    param_substitution: Final = "{param:" + param_name + "}"
    config_item_store.put(
        DdbConfigItem(
            organization_id="",
            remote_account_ids=list(chain(remote_account_ids, [param_substitution])),
        )
    )

    yield list(chain(remote_account_ids, [param_value]))


dt: Final = datetime(2024, 2, 16, 9, 38, tzinfo=timezone.utc)


@freeze_time(dt)
def test_orchestrator_invokes_all_accounts(remote_accounts: list[str]) -> None:
    asg_scheduler_name: Final = "my-asg-scheduler"
    env: Final = MockAsgOrchestratorEnvironment(
        asg_scheduler_name=asg_scheduler_name,
        enable_schedule_hub_account=True,
        schedule_regions=[],
    )

    mock_lambda: Final = MagicMock()
    mock_lambda.invoke = MagicMock(return_value={"StatusCode": 200})

    with (
        patch(
            "instance_scheduler.handler.asg_orchestrator.get_client_with_standard_retry",
            lambda x: {"lambda": mock_lambda}[x],
        ),
    ):
        orchestrate_asgs(env, MockLambdaContext())

    assert mock_lambda.invoke.call_count == 4
    default_region: Final = Session().region_name
    called_accounts: Final = set()
    for call_args in mock_lambda.invoke.call_args_list:
        assert call_args.kwargs["FunctionName"] == asg_scheduler_name
        assert call_args.kwargs["InvocationType"] == "Event"
        payload: SchedulingRequest = json.loads(call_args.kwargs["Payload"])
        assert datetime.fromisoformat(payload["dispatch_time"]) == dt
        called_accounts.add(payload["account"])
        assert payload["service"] == "asg"
        assert payload["region"] == default_region
        assert datetime.fromisoformat(payload["current_dt"]) == dt

    assert len(called_accounts) == 4
    assert called_accounts == set(chain([DEFAULT_ACCOUNT_ID], remote_accounts))


@freeze_time(dt)
def test_orchestrator_invokes_remote_accounts_only(remote_accounts: list[str]) -> None:
    asg_scheduler_name: Final = "my-asg-scheduler"
    env: Final = MockAsgOrchestratorEnvironment(
        asg_scheduler_name=asg_scheduler_name,
        enable_schedule_hub_account=False,
        schedule_regions=[],
    )

    mock_lambda: Final = MagicMock()
    mock_lambda.invoke = MagicMock(return_value={"StatusCode": 200})

    with (
        patch(
            "instance_scheduler.handler.asg_orchestrator.get_client_with_standard_retry",
            lambda x: {"lambda": mock_lambda}[x],
        ),
    ):
        orchestrate_asgs(env, MockLambdaContext())

    assert mock_lambda.invoke.call_count == 3
    default_region: Final = Session().region_name
    called_accounts: Final = set()
    for call_args in mock_lambda.invoke.call_args_list:
        assert call_args.kwargs["FunctionName"] == asg_scheduler_name
        assert call_args.kwargs["InvocationType"] == "Event"
        payload: SchedulingRequest = json.loads(call_args.kwargs["Payload"])
        assert datetime.fromisoformat(payload["dispatch_time"]) == dt
        called_accounts.add(payload["account"])
        assert payload["service"] == "asg"
        assert payload["region"] == default_region
        assert datetime.fromisoformat(payload["current_dt"]) == dt

    assert len(called_accounts) == 3
    assert called_accounts == set(remote_accounts)


@freeze_time(dt)
def test_orchestrator_invokes_across_regions(remote_accounts: list[str]) -> None:
    asg_scheduler_name: Final = "my-asg-scheduler"
    schedule_regions: Final = ["us-east-1", "us-west-2", "ap-southeast-1"]
    env: Final = MockAsgOrchestratorEnvironment(
        asg_scheduler_name=asg_scheduler_name,
        enable_schedule_hub_account=True,
        schedule_regions=schedule_regions,
    )

    mock_lambda: Final = MagicMock()
    mock_lambda.invoke = MagicMock(return_value={"StatusCode": 200})

    with (
        patch(
            "instance_scheduler.handler.asg_orchestrator.get_client_with_standard_retry",
            lambda x: {"lambda": mock_lambda}[x],
        ),
    ):
        orchestrate_asgs(env, MockLambdaContext())

    assert mock_lambda.invoke.call_count == 12
    called_account_regions: Final = set()
    for call_args in mock_lambda.invoke.call_args_list:
        assert call_args.kwargs["FunctionName"] == asg_scheduler_name
        assert call_args.kwargs["InvocationType"] == "Event"
        payload: SchedulingRequest = json.loads(call_args.kwargs["Payload"])
        assert datetime.fromisoformat(payload["dispatch_time"]) == dt
        called_account_regions.add((payload["account"], payload["region"]))
        assert payload["service"] == "asg"
        assert datetime.fromisoformat(payload["current_dt"]) == dt

    assert len(called_account_regions) == 12
    assert called_account_regions == set(
        product(chain([DEFAULT_ACCOUNT_ID], remote_accounts), schedule_regions)
    )
