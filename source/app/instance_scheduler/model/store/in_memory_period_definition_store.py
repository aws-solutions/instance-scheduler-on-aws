# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from typing import Any, Mapping, Optional, Sequence, TypeGuard

from instance_scheduler.model.period_definition import (
    PeriodDefinition,
    PeriodParams,
    validate_as_period_params,
)
from instance_scheduler.model.store.period_definition_store import (
    PeriodAlreadyExistsException,
    PeriodDefinitionStore,
    UnknownPeriodException,
)
from instance_scheduler.util.validation import ValidationException

SerializedInMemoryPeriodDefinitionStore = Sequence[PeriodParams]


class InMemoryPeriodDefinitionStore(PeriodDefinitionStore):
    _data: dict[str, PeriodDefinition]

    def __init__(self, initial_data: Optional[Mapping[str, PeriodDefinition]] = None):
        self._data = dict(initial_data) if initial_data else {}

    def put(self, period: PeriodDefinition, overwrite: bool = False) -> None:
        if not overwrite and period.name in self._data:
            raise PeriodAlreadyExistsException(f"period {period.name} already exists")

        self._data[period.name] = period

    def delete(self, period_name: str, error_if_missing: bool = False) -> None:
        if error_if_missing and period_name not in self._data:
            raise UnknownPeriodException(f"period {period_name} does not exist")

        self._data.pop(period_name, None)

    def find_by_name(self, period_name: str) -> Optional[PeriodDefinition]:
        return self._data.get(period_name, None)

    def find_all(self) -> Mapping[str, PeriodDefinition]:
        return self._data

    def serialize(self) -> SerializedInMemoryPeriodDefinitionStore:
        return [period_def.to_period_params() for period_def in self._data.values()]

    @classmethod
    def deserialize(
        cls, data: SerializedInMemoryPeriodDefinitionStore
    ) -> "InMemoryPeriodDefinitionStore":
        periods: dict[str, PeriodDefinition] = {}
        for period_params in data:
            period_def = PeriodDefinition.from_period_params(period_params)
            periods[period_def.name] = period_def

        return InMemoryPeriodDefinitionStore(periods)

    @staticmethod
    def validate_serial_data(
        data: Any,
    ) -> TypeGuard[SerializedInMemoryPeriodDefinitionStore]:
        if not isinstance(data, Sequence):
            raise ValidationException(
                f"Invalid PeriodStore format: must be a sequence of period definitions, received: {type(data)}"
            )

        for params in data:
            if not isinstance(params, dict):
                raise ValidationException(
                    f"Invalid PeriodStore format: must be a sequence of PeriodParams, Sequence contains {type(data)}"
                )
            validate_as_period_params(params)

        return True
