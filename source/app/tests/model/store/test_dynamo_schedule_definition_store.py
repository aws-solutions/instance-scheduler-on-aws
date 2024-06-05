# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from typing import TYPE_CHECKING

import boto3
import pytest
from _pytest.fixtures import fixture
from botocore.exceptions import ClientError

from instance_scheduler.model.period_identifier import PeriodIdentifier
from instance_scheduler.model.schedule_definition import ScheduleDefinition
from instance_scheduler.model.store.dynamo_schedule_definition_store import (
    DynamoScheduleDefinitionStore,
)
from tests.test_utils.unordered_list import UnorderedList

if TYPE_CHECKING:
    from mypy_boto3_dynamodb.client import DynamoDBClient
else:
    DynamoDBClient = object


@fixture
def schedule_store(config_table: str) -> DynamoScheduleDefinitionStore:
    return DynamoScheduleDefinitionStore(config_table)


def test_read_invalid_schedule_returns_exception_gracefully(
    config_table: str,
    schedule_store: DynamoScheduleDefinitionStore,
) -> None:
    ddb_client: DynamoDBClient = boto3.client("dynamodb")
    ddb_client.put_item(
        TableName=config_table,
        Item={
            "type": {"S": "schedule"},
            "name": {"S": "invalid-schedule"},
        },
    )

    schedule_store.put(
        ScheduleDefinition(name="simple_valid_schedule", override_status="running")
    )

    schedules, errors = schedule_store.find_all_with_errors()
    assert len(schedules) == 1
    assert len(errors) == 1

    assert len(schedule_store.find_all()) == 1


def test_read_schedule_with_deprecated_use_metrics_flag_does_not_error(
    config_table: str,
    schedule_store: DynamoScheduleDefinitionStore,
) -> None:
    ddb_client: DynamoDBClient = boto3.client("dynamodb")
    ddb_client.put_item(
        TableName=config_table,
        Item={
            "type": {"S": "schedule"},
            "name": {"S": "my_schedule"},
            "override_status": {"S": "running"},
            "use_metrics": {"BOOL": True},
        },
    )

    schedule_store.put(
        ScheduleDefinition(name="simple_valid_schedule", override_status="running")
    )

    schedules, errors = schedule_store.find_all_with_errors()
    assert len(schedules) == 2
    assert len(errors) == 0

    assert len(schedule_store.find_all()) == 2


def test_transact_put_then_read_simple_schedule(
    schedule_store: DynamoScheduleDefinitionStore,
) -> None:
    schedule = ScheduleDefinition(name="test_schedule", override_status="running")

    with schedule_store.new_transaction() as transaction:
        transaction.add(schedule_store.transact_put(schedule))

    fetched = schedule_store.find_by_name("test_schedule")
    assert schedule == fetched


def test_transact_put_then_read_complex_schedule(
    schedule_store: DynamoScheduleDefinitionStore,
) -> None:
    schedule = ScheduleDefinition(
        name="test_schedule",
        stop_new_instances=True,
        retain_running=True,
        hibernate=False,
        configured_in_stack="some-stack-arn",
        enforced=True,
        ssm_maintenance_window=["some-window"],
        description="some description",
        timezone="Europe/Berlin",
        periods=UnorderedList(
            [PeriodIdentifier("test_period1"), PeriodIdentifier("test_period2")]
        ),
    )

    with schedule_store.new_transaction() as transaction:
        transaction.add(schedule_store.transact_put(schedule))

    fetched = schedule_store.find_by_name("test_schedule")
    assert schedule == fetched


def test_transact_put_schedule_with_overwrite(
    schedule_store: DynamoScheduleDefinitionStore,
) -> None:
    # 1st put
    schedule1 = ScheduleDefinition(name="test_schedule", override_status="running")
    with schedule_store.new_transaction() as transaction:
        transaction.add(schedule_store.transact_put(schedule1, overwrite=True))
    fetched = schedule_store.find_by_name("test_schedule")
    assert fetched == schedule1

    # 2nd put (overwrite)
    schedule2 = ScheduleDefinition(name="test_schedule", override_status="stopped")
    with schedule_store.new_transaction() as transaction:
        transaction.add(schedule_store.transact_put(schedule2, overwrite=True))
    fetched = schedule_store.find_by_name("test_schedule")
    assert fetched == schedule2


def test_transact_put_rejects_overwrite_when_flag_not_set(
    schedule_store: DynamoScheduleDefinitionStore,
) -> None:
    schedule = ScheduleDefinition(name="test_schedule", override_status="running")

    schedule_store.put(schedule)
    with pytest.raises(ClientError):
        with schedule_store.new_transaction() as transaction:
            transaction.add(schedule_store.transact_put(schedule))


def test_transact_delete_errors_when_missing_if_enabled(
    schedule_store: DynamoScheduleDefinitionStore,
) -> None:
    with pytest.raises(ClientError):
        with schedule_store.new_transaction() as transaction:
            transaction.add(
                schedule_store.transact_delete("non-existing", error_if_missing=True)
            )


def test_transact_delete_on_missing_passes_if_error_flag_disabled(
    schedule_store: DynamoScheduleDefinitionStore,
) -> None:
    with schedule_store.new_transaction() as transaction:
        transaction.add(
            schedule_store.transact_delete("non-existing")
        )  # default behavior is false


def test_transact_delete_deletes_correctly(
    schedule_store: DynamoScheduleDefinitionStore,
) -> None:
    schedule = ScheduleDefinition(name="test-schedule", override_status="running")

    schedule_store.put(schedule)
    assert len(schedule_store.find_all()) == 1
    with schedule_store.new_transaction() as transaction:
        transaction.add(
            schedule_store.transact_delete(schedule.name, error_if_missing=True)
        )
    assert len(schedule_store.find_all()) == 0
