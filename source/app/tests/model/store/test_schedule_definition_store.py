# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import pytest
from _pytest.fixtures import SubRequest, fixture

from instance_scheduler.model.period_definition import PeriodDefinition
from instance_scheduler.model.period_identifier import PeriodIdentifier
from instance_scheduler.model.schedule_definition import ScheduleDefinition
from instance_scheduler.model.store.dynamo_schedule_definition_store import (
    DynamoScheduleDefinitionStore,
)
from instance_scheduler.model.store.in_memory_schedule_definition_store import (
    InMemoryScheduleDefinitionStore,
)
from instance_scheduler.model.store.schedule_definition_store import (
    ScheduleAlreadyExistsException,
    ScheduleDefinitionStore,
    UnknownScheduleException,
)
from tests.test_utils.unordered_list import UnorderedList


@fixture(params=["dynamo", "in-memory"])
def schedule_store(request: SubRequest) -> ScheduleDefinitionStore:
    match request.param:
        case "dynamo":
            return DynamoScheduleDefinitionStore(
                request.getfixturevalue(argname="config_table")
            )
        case "in-memory":
            return InMemoryScheduleDefinitionStore()
        case _:
            raise ValueError


def test_put_then_read_simple_schedule(schedule_store: ScheduleDefinitionStore) -> None:
    schedule = ScheduleDefinition(
        name="test_schedule", periods=[PeriodIdentifier("period_name")]
    )

    schedule_store.put(schedule)
    fetched = schedule_store.find_by_name("test_schedule")
    assert schedule == fetched


def test_put_then_read_override_status_only_schedule(
    schedule_store: ScheduleDefinitionStore,
) -> None:
    schedule = ScheduleDefinition(name="test_schedule", override_status="running")

    schedule_store.put(schedule)
    fetched = schedule_store.find_by_name("test_schedule")
    assert schedule == fetched


def test_put_then_read_complex_schedule(
    schedule_store: ScheduleDefinitionStore,
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

    schedule_store.put(schedule)
    fetched = schedule_store.find_by_name("test_schedule")
    assert schedule == fetched


def test_put_schedule_rejects_overwrite_when_flag_not_set(
    schedule_store: ScheduleDefinitionStore,
) -> None:
    schedule = ScheduleDefinition(name="test_schedule", override_status="running")

    schedule_store.put(schedule)
    with pytest.raises(ScheduleAlreadyExistsException):
        schedule_store.put(schedule)


def test_put_schedule_with_overwrite(schedule_store: ScheduleDefinitionStore) -> None:
    # 1st put
    schedule1 = ScheduleDefinition(name="test_schedule", override_status="running")
    schedule_store.put(schedule1, overwrite=True)
    fetched = schedule_store.find_by_name("test_schedule")
    assert fetched == schedule1

    # 2nd put (overwrite)
    schedule2 = ScheduleDefinition(name="test_schedule", override_status="stopped")
    schedule_store.put(schedule2, overwrite=True)
    fetched = schedule_store.find_by_name("test_schedule")
    assert fetched == schedule2


def test_find_schedule_returns_null_when_not_exists(
    schedule_store: ScheduleDefinitionStore,
) -> None:
    fetched = schedule_store.find_by_name("non-existing")
    assert fetched is None


def test_find_all_returns_empty_map_when_none_exist(
    schedule_store: ScheduleDefinitionStore,
) -> None:
    fetched = schedule_store.find_all()
    assert fetched == {}


def test_find_all_returns_all_expected(
    schedule_store: ScheduleDefinitionStore, config_table: str
) -> None:
    schedule1 = ScheduleDefinition(name="test_schedule1", override_status="running")
    schedule2 = ScheduleDefinition(name="test_schedule2", override_status="stopped")
    schedule3 = ScheduleDefinition(
        name="test_schedule3",
        periods=[PeriodIdentifier.of("period", "m2.micro")],
    )

    schedule_store.put(schedule1)
    schedule_store.put(schedule2)
    schedule_store.put(schedule3)

    fetched = schedule_store.find_all()

    assert fetched == {
        "test_schedule1": schedule1,
        "test_schedule2": schedule2,
        "test_schedule3": schedule3,
    }


def test_find_all_when_schedules_share_a_period(
    schedule_store: ScheduleDefinitionStore,
) -> None:
    schedule1 = ScheduleDefinition(
        name="schedule1",
        periods=[PeriodIdentifier.of("period", "m2.micro")],
    )
    schedule2 = ScheduleDefinition(
        name="schedule2",
        periods=[PeriodIdentifier.of("period", "m4.large")],
    )

    schedule_store.put(schedule1, overwrite=True)
    schedule_store.put(schedule2, overwrite=True)

    fetched = schedule_store.find_all()

    assert fetched == {
        "schedule1": schedule1,
        "schedule2": schedule2,
    }


def test_find_by_period_returns_expected(
    schedule_store: ScheduleDefinitionStore,
) -> None:
    rpd = PeriodDefinition(name="used_period", begintime="10:00")

    schedule1 = ScheduleDefinition(
        name="schedule1",
        periods=[PeriodIdentifier.of(rpd.name)],
    )
    schedule2 = ScheduleDefinition(
        name="schedule2",
        periods=[PeriodIdentifier.of(rpd.name, "m4.large")],
    )
    schedule3 = ScheduleDefinition(
        name="schedule3",
        periods=[PeriodIdentifier.of("some_other_period")],
    )
    schedule_store.put(schedule1)
    schedule_store.put(schedule2)
    schedule_store.put(schedule3)

    fetched = schedule_store.find_by_period("used_period")

    assert fetched == {
        "schedule1": schedule1,
        "schedule2": schedule2,
    }


def test_delete_errors_when_missing_if_enabled(
    schedule_store: ScheduleDefinitionStore,
) -> None:
    with pytest.raises(UnknownScheduleException):
        schedule_store.delete("non-existing", error_if_missing=True)


def test_delete_on_missing_passes_if_error_flag_disabled(
    schedule_store: ScheduleDefinitionStore,
) -> None:
    schedule_store.delete("non-existing")  # default behavior is false


def test_delete_deletes_correctly(schedule_store: ScheduleDefinitionStore) -> None:
    schedule = ScheduleDefinition(name="test-schedule", override_status="running")

    schedule_store.put(schedule)
    assert len(schedule_store.find_all()) == 1
    schedule_store.delete(schedule.name, error_if_missing=True)
    assert len(schedule_store.find_all()) == 0
