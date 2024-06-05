# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import pytest
from _pytest.fixtures import SubRequest, fixture

from instance_scheduler.model.period_definition import PeriodDefinition
from instance_scheduler.model.store.dynamo_period_definition_store import (
    DynamoPeriodDefinitionStore,
)
from instance_scheduler.model.store.in_memory_period_definition_store import (
    InMemoryPeriodDefinitionStore,
)
from instance_scheduler.model.store.period_definition_store import (
    PeriodAlreadyExistsException,
    PeriodDefinitionStore,
    UnknownPeriodException,
)


@fixture(params=["dynamo", "in-memory"])
def period_store(request: SubRequest) -> PeriodDefinitionStore:
    match request.param:
        case "dynamo":
            return DynamoPeriodDefinitionStore(
                request.getfixturevalue(argname="config_table")
            )
        case "in-memory":
            return InMemoryPeriodDefinitionStore()
        case _:
            raise ValueError()


def test_write_then_read_simple_period(
    period_store: PeriodDefinitionStore,
) -> None:
    rpd = PeriodDefinition(name="test-period", begintime="05:00")

    period_store.put(rpd)
    fetched = period_store.find_by_name("test-period")
    assert rpd == fetched


def test_write_then_read_complex_period(
    period_store: PeriodDefinitionStore,
) -> None:
    rpd = PeriodDefinition(
        name="test-period",
        begintime="05:00",
        endtime="06:00",
        months={"jan"},
        monthdays={"1-5"},
        weekdays={"mon-fri"},
        description="some random description",
    )

    period_store.put(rpd)
    fetched = period_store.find_by_name("test-period")
    assert rpd == fetched


def test_overwrite_then_read(period_store: PeriodDefinitionStore) -> None:
    # write first
    rpd = PeriodDefinition(name="test-period", begintime="05:00")
    period_store.put(rpd, overwrite=True)

    fetched = period_store.find_by_name("test-period")
    assert rpd == fetched

    # then overwrite
    new_rpd = PeriodDefinition(name="test-period", begintime="10:00")
    period_store.put(new_rpd, overwrite=True)

    fetched = period_store.find_by_name("test-period")
    assert new_rpd == fetched
    assert rpd != fetched


def test_overwrite_is_rejected_when_flag_not_set(
    period_store: PeriodDefinitionStore,
) -> None:
    rpd = PeriodDefinition(name="test-period", begintime="05:00")

    period_store.put(rpd)
    with pytest.raises(PeriodAlreadyExistsException):
        period_store.put(rpd)


def test_find_all_returns_all_expected(
    period_store: PeriodDefinitionStore, config_table: str
) -> None:
    rpd1 = PeriodDefinition(name="test-period1", begintime="05:00")
    rpd2 = PeriodDefinition(name="test-period2", monthdays={"12-24"})
    rpd3 = PeriodDefinition(name="test-period3", begintime="05:00", endtime="10:00")

    period_store.put(rpd1)
    period_store.put(rpd2)
    period_store.put(rpd3)

    fetched = period_store.find_all()
    assert fetched == {
        "test-period1": rpd1,
        "test-period2": rpd2,
        "test-period3": rpd3,
    }


def test_delete_errors_when_missing_if_enabled(
    period_store: PeriodDefinitionStore,
) -> None:
    with pytest.raises(UnknownPeriodException):
        period_store.delete("non-existing", error_if_missing=True)


def test_delete_on_missing_passes_if_error_flag_disabled(
    period_store: PeriodDefinitionStore,
) -> None:
    period_store.delete("non-existing")  # default behavior is false


def test_delete_deletes_correctly(period_store: PeriodDefinitionStore) -> None:
    rpd = PeriodDefinition(name="test-period", begintime="05:00")

    period_store.put(rpd)
    assert len(period_store.find_all()) == 1
    period_store.delete(rpd.name, error_if_missing=True)
    assert len(period_store.find_all()) == 0
