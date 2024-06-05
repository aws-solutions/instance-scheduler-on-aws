# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from typing import TYPE_CHECKING

import boto3
import pytest
from _pytest.fixtures import fixture
from botocore.exceptions import ClientError

from instance_scheduler.model.period_definition import PeriodDefinition
from instance_scheduler.model.store.ddb_transact_write import WriteTransaction
from instance_scheduler.model.store.dynamo_period_definition_store import (
    DynamoPeriodDefinitionStore,
)

if TYPE_CHECKING:
    from mypy_boto3_dynamodb.client import DynamoDBClient
else:
    DynamoDBClient = object


@fixture
def period_store(config_table: str) -> DynamoPeriodDefinitionStore:
    return DynamoPeriodDefinitionStore(config_table)


def test_read_invalid_period_returns_exception_gracefully(
    config_table: str,
    period_store: DynamoPeriodDefinitionStore,
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

    period_store.put(PeriodDefinition(name="simple_valid_period", begintime="05:00"))

    periods, errors = period_store.find_all_with_errors()
    assert len(periods) == 1
    assert len(errors) == 1

    assert len(period_store.find_all()) == 1


def test_transaction_write_then_read(
    period_store: DynamoPeriodDefinitionStore,
) -> None:
    rpd = PeriodDefinition(name="test-period", begintime="05:00")

    with WriteTransaction(boto3.client("dynamodb")) as transaction:
        transaction.add(period_store.transact_put(rpd))

    fetched = period_store.find_by_name("test-period")
    assert rpd == fetched


def test_transaction_overwrite_then_read(
    period_store: DynamoPeriodDefinitionStore,
) -> None:
    rpd = PeriodDefinition(name="test-period", begintime="05:00")

    # write first
    with WriteTransaction(boto3.client("dynamodb")) as transaction:
        transaction.add(period_store.transact_put(rpd, overwrite=True))

    fetched = period_store.find_by_name("test-period")
    assert rpd == fetched

    # then overwrite
    new_rpd = PeriodDefinition(name="test-period", begintime="10:00")

    with WriteTransaction(boto3.client("dynamodb")) as transaction:
        transaction.add(period_store.transact_put(new_rpd, overwrite=True))

    fetched = period_store.find_by_name("test-period")
    assert new_rpd == fetched
    assert rpd != fetched


def test_transaction_overwrite_is_rejected_when_flag_not_set(
    period_store: DynamoPeriodDefinitionStore,
) -> None:
    rpd = PeriodDefinition(name="test-period", begintime="05:00")

    period_store.put(rpd)
    with pytest.raises(ClientError):
        with WriteTransaction(boto3.client("dynamodb")) as transaction:
            transaction.add(period_store.transact_put(rpd))


def test_transact_delete_errors_when_missing_if_enabled(
    period_store: DynamoPeriodDefinitionStore,
) -> None:
    with pytest.raises(ClientError):
        with WriteTransaction(boto3.client("dynamodb")) as transaction:
            transaction.add(
                period_store.transact_delete("non-existing", error_if_missing=True)
            )


def test_transact_delete_on_missing_passes_if_error_flag_disabled(
    period_store: DynamoPeriodDefinitionStore,
) -> None:
    with WriteTransaction(boto3.client("dynamodb")) as transaction:
        transaction.add(
            period_store.transact_delete("non-existing")
        )  # default behavior is false


def test_transact_delete_deletes_correctly(
    period_store: DynamoPeriodDefinitionStore,
) -> None:
    rpd = PeriodDefinition(name="test-period", begintime="05:00")

    period_store.put(rpd)
    assert len(period_store.find_all()) == 1
    with WriteTransaction(boto3.client("dynamodb")) as transaction:
        transaction.add(period_store.transact_delete(rpd.name, error_if_missing=True))
    assert len(period_store.find_all()) == 0
