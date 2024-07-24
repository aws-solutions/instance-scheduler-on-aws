# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from typing import Iterator
from unittest.mock import patch

import boto3
from pytest import fixture

from instance_scheduler.handler.config_resource import (
    SchedulerSetupHandler,
    ServiceSetupRequest,
    ServiceSetupResourceProperties,
    is_org_id,
)
from instance_scheduler.handler.environments.main_lambda_environment import (
    MainLambdaEnv,
)
from instance_scheduler.handler.setup_demo_data import DEMO_PERIODS, DEMO_SCHEDULES
from instance_scheduler.model.ddb_config_item import DdbConfigItem
from instance_scheduler.model.schedule_definition import ScheduleDefinition
from instance_scheduler.model.store.ddb_config_item_store import DdbConfigItemStore
from instance_scheduler.model.store.period_definition_store import PeriodDefinitionStore
from instance_scheduler.model.store.schedule_definition_store import (
    ScheduleDefinitionStore,
)
from instance_scheduler.util.custom_resource import CustomResourceRequest
from tests.context import MockLambdaContext
from tests.test_utils.mock_main_lambda_env import MockMainLambdaEnv
from tests.test_utils.unordered_list import UnorderedList

stack_arn = "arn:aws:cloudformation:us-west-2:123456789012:stack/teststack/51af3dc0-da77-11e4-872e-1234567db123"


@fixture(autouse=True)
def intercept_cfn_responses() -> Iterator[None]:
    with patch.object(SchedulerSetupHandler, "_send_response"):
        yield


def new_create_request(
    resource_properties: ServiceSetupResourceProperties,
) -> ServiceSetupRequest:
    return {
        "RequestType": "Create",
        "ServiceToken": "LambdaARN",
        "ResponseURL": "url",
        "StackId": stack_arn,
        "RequestId": "requestId",
        "ResourceType": "Custom::ServiceInstanceSchedule",
        "LogicalResourceId": "CFNLogicalID",
        "PhysicalResourceId": "PhysicalID",
        "ResourceProperties": resource_properties,
    }


def new_update_request(
    resource_properties: ServiceSetupResourceProperties,
    old_resource_properties: ServiceSetupResourceProperties,
) -> CustomResourceRequest[ServiceSetupResourceProperties]:
    return {
        "RequestType": "Update",
        "ServiceToken": "LambdaARN",
        "ResponseURL": "url",
        "StackId": stack_arn,
        "RequestId": "requestId",
        "ResourceType": "Custom::ServiceInstanceSchedule",
        "LogicalResourceId": "CFNLogicalID",
        "PhysicalResourceId": "PhysicalID",
        "ResourceProperties": resource_properties,
        "OldResourceProperties": old_resource_properties,
    }


def test_a_valid_org_id_pattern() -> None:
    assert is_org_id("o-a1b1c3d4e5")


def test_an_invalid_org_id_pattern() -> None:
    assert not is_org_id("111111111111,222222222222")


def test_create_request_no_orgs_or_accounts(
    config_item_store: DdbConfigItemStore,
) -> None:
    event = new_create_request(
        {
            "timeout": 120,
            "log_retention_days": 7,
            "remote_account_ids": [],
        }
    )
    handler = SchedulerSetupHandler(event, MockLambdaContext(), MockMainLambdaEnv())
    handler.handle_request()

    saved_item = config_item_store.get()
    assert saved_item == DdbConfigItem(remote_account_ids=[], organization_id="")


def test_create_request_with_account_ids(config_item_store: DdbConfigItemStore) -> None:
    accounts = ["111111111111", "222222222222"]
    event = new_create_request(
        {
            "timeout": 120,
            "log_retention_days": 7,
            "remote_account_ids": accounts,
        }
    )
    handler = SchedulerSetupHandler(event, MockLambdaContext(), MockMainLambdaEnv())
    handler.handle_request()

    saved_item = config_item_store.get()
    assert saved_item == DdbConfigItem(
        remote_account_ids=["111111111111", "222222222222"], organization_id=""
    )


def test_create_request_with_orgs(config_item_store: DdbConfigItemStore) -> None:
    """Happy path, orgs_disabled"""
    SchedulerSetupHandler(
        new_create_request(
            {
                "timeout": 120,
                "log_retention_days": 7,
                "remote_account_ids": ["o-a1b1c3d4e5"],
            }
        ),
        MockLambdaContext(),
        MockMainLambdaEnv(enable_aws_organizations=True),
    ).handle_request()

    saved_item = config_item_store.get()
    assert saved_item == DdbConfigItem(
        remote_account_ids=[], organization_id="o-a1b1c3d4e5"
    )


def test_update_request_preserves_registered_accounts_when_org_doesnt_change(
    config_item_store: DdbConfigItemStore,
) -> None:
    config_item_store.put(
        DdbConfigItem(
            organization_id="o-a1b1c3d4e5",
            remote_account_ids=["111122223333", "222233334444"],
        )
    )
    SchedulerSetupHandler(
        new_update_request(
            {
                "timeout": 120,
                "log_retention_days": 7,
                "remote_account_ids": ["o-a1b1c3d4e5"],
            },
            {
                "timeout": 120,
                "log_retention_days": 30,
                "remote_account_ids": ["o-a1b1c3d4e5"],
            },
        ),
        MockLambdaContext(),
        MockMainLambdaEnv(enable_aws_organizations=True),
    ).handle_request()

    saved_item = config_item_store.get()
    assert saved_item == DdbConfigItem(
        remote_account_ids=["111122223333", "222233334444"],
        organization_id="o-a1b1c3d4e5",
    )


def test_update_request_clears_registered_accounts_when_org_changes(
    config_item_store: DdbConfigItemStore,
) -> None:
    config_item_store.put(
        DdbConfigItem(
            organization_id="o-abcdefghijkl",
            remote_account_ids=["111122223333", "222233334444"],
        )
    )
    SchedulerSetupHandler(
        new_update_request(
            {
                "timeout": 120,
                "log_retention_days": 7,
                "remote_account_ids": ["o-a1b1c3d4e5"],
            },
            {
                "timeout": 120,
                "log_retention_days": 7,
                "remote_account_ids": ["o-abcdefghijkl"],
            },
        ),
        MockLambdaContext(),
        MockMainLambdaEnv(enable_aws_organizations=True),
    ).handle_request()

    saved_item = config_item_store.get()
    assert saved_item == DdbConfigItem(
        remote_account_ids=[],
        organization_id="o-a1b1c3d4e5",
    )


def test_update_request_overwrites_remote_accounts_when_orgs_disabled(
    config_item_store: DdbConfigItemStore,
) -> None:
    config_item_store.put(
        DdbConfigItem(
            organization_id="o-abcdefghijkl",
            remote_account_ids=["111122223333", "222233334444"],
        )
    )
    SchedulerSetupHandler(
        new_update_request(
            {
                "timeout": 120,
                "log_retention_days": 7,
                "remote_account_ids": ["333344445555", "444455556666"],
            },
            {
                "timeout": 120,
                "log_retention_days": 7,
                "remote_account_ids": ["o-abcdefghijkl"],
            },
        ),
        MockLambdaContext(),
        MockMainLambdaEnv(enable_aws_organizations=False),
    ).handle_request()

    saved_item = config_item_store.get()
    assert saved_item == DdbConfigItem(
        remote_account_ids=["333344445555", "444455556666"],
        organization_id="",
    )


def test_sets_lambda_logs_retention_period_on_create(
    test_suite_env: MainLambdaEnv, config_item_store: DdbConfigItemStore
) -> None:
    """With no period, expect set to default"""
    log_group = test_suite_env.log_group
    handler = SchedulerSetupHandler(
        new_create_request(
            {"timeout": 120, "remote_account_ids": [], "log_retention_days": 30}
        ),
        MockLambdaContext(log_group),
        MockMainLambdaEnv(),
    )
    handler.handle_request()
    response = boto3.client("logs").describe_log_groups(logGroupNamePrefix=log_group)
    assert response["logGroups"][0]["logGroupName"] == log_group
    assert response["logGroups"][0]["retentionInDays"] == 30


def test_creates_example_schedules_on_create(
    config_item_store: DdbConfigItemStore,
    period_store: PeriodDefinitionStore,
    schedule_store: ScheduleDefinitionStore,
) -> None:
    event = new_create_request(
        {
            "timeout": 120,
            "log_retention_days": 7,
            "remote_account_ids": [],
        }
    )
    handler = SchedulerSetupHandler(event, MockLambdaContext(), MockMainLambdaEnv())
    handler.handle_request()

    saved_schedules = list(schedule_store.find_all().values())
    saved_periods = list(period_store.find_all().values())

    demo_schedules_with_unordered_periods = [
        ScheduleDefinition(
            name=orig.name,
            description=orig.description,
            periods=UnorderedList(orig.periods),
            timezone=orig.timezone,
            override_status=orig.override_status,
        )
        for orig in DEMO_SCHEDULES
    ]

    assert saved_schedules == UnorderedList(demo_schedules_with_unordered_periods)
    assert saved_periods == UnorderedList(DEMO_PERIODS)
