# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import pytest
from _pytest.fixtures import fixture

from instance_scheduler.model.period_definition import PeriodDefinition, PeriodParams
from instance_scheduler.model.store.in_memory_period_definition_store import (
    InMemoryPeriodDefinitionStore,
)
from instance_scheduler.util.validation import ValidationException


@fixture
def period_store() -> InMemoryPeriodDefinitionStore:
    return InMemoryPeriodDefinitionStore()


def test_serialize_then_deserialize(
    period_store: InMemoryPeriodDefinitionStore,
) -> None:
    period_store.put(PeriodDefinition("period1", begintime="05:00", endtime="10:00"))
    period_store.put(PeriodDefinition("period2", weekdays={"Mon-Fri"}))
    period_store.put(PeriodDefinition("period3", monthdays={"1-5"}))
    period_store.put(PeriodDefinition("period4", months={"Jan-Feb"}))

    serial_data = period_store.serialize()

    # ensure returned data matches own validation
    period_store.validate_serial_data(serial_data)

    deserialized_store = InMemoryPeriodDefinitionStore.deserialize(serial_data)

    assert deserialized_store.find_all() == period_store.find_all()


def test_validate_rejects_malformed_input() -> None:
    with pytest.raises(ValidationException):
        # not a sequence
        InMemoryPeriodDefinitionStore.validate_serial_data({})

    with pytest.raises(ValidationException):
        # contained data is not a dict
        InMemoryPeriodDefinitionStore.validate_serial_data(["something-invalid"])

    with pytest.raises(ValidationException):
        # contained data is not valid PeriodParams
        InMemoryPeriodDefinitionStore.validate_serial_data(
            [PeriodParams(name="aPeriod"), {"invalid-key": "something-invalid"}]
        )
