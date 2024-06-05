# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import pytest
from _pytest.fixtures import fixture

from instance_scheduler.model.period_identifier import PeriodIdentifier
from instance_scheduler.model.schedule_definition import (
    ScheduleDefinition,
    ScheduleParams,
)
from instance_scheduler.model.store.in_memory_schedule_definition_store import (
    InMemoryScheduleDefinitionStore,
)
from instance_scheduler.util.validation import ValidationException


@fixture
def schedule_store() -> InMemoryScheduleDefinitionStore:
    return InMemoryScheduleDefinitionStore()


def test_serialize_then_deserialize(
    schedule_store: InMemoryScheduleDefinitionStore,
) -> None:
    schedule_store.put(
        ScheduleDefinition(name="override-sched", override_status="running")
    )
    schedule_store.put(
        ScheduleDefinition(
            name="basic-sched", periods=[PeriodIdentifier.of("period1", "some_size")]
        )
    )
    schedule_store.put(
        ScheduleDefinition(
            name="sched-with-everything-true",
            periods=[PeriodIdentifier.of("period1", "some_size")],
            timezone="Asia/Tokyo",
            description="some description",
            stop_new_instances=True,
            ssm_maintenance_window=["some-window"],
            enforced=True,
            hibernate=True,
            retain_running=True,
            configured_in_stack="some-stack-arn",
        )
    )
    schedule_store.put(
        ScheduleDefinition(
            name="sched-with-everything-false",
            periods=[PeriodIdentifier.of("period1", "some_size")],
            timezone="Asia/Tokyo",
            description="some description",
            stop_new_instances=False,
            ssm_maintenance_window=["some-window"],
            enforced=False,
            hibernate=False,
            retain_running=False,
            configured_in_stack="some-stack-arn",
        )
    )

    serialized_store = schedule_store.serialize()

    # ensure returned data matches own validation
    schedule_store.validate_serial_data(serialized_store)

    deserialized_store = InMemoryScheduleDefinitionStore.deserialize(serialized_store)

    assert deserialized_store.find_all() == schedule_store.find_all()


def test_validate_rejects_malformed_input() -> None:
    with pytest.raises(ValidationException):
        # not a sequence
        InMemoryScheduleDefinitionStore.validate_serial_data({})

    with pytest.raises(ValidationException):
        # contained data is not a dict
        InMemoryScheduleDefinitionStore.validate_serial_data(["something-invalid"])

    with pytest.raises(ValidationException):
        # contained data is not valid PeriodParams
        InMemoryScheduleDefinitionStore.validate_serial_data(
            [ScheduleParams(name="a Schedule"), {"invalid-key": "something-invalid"}]
        )
