# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from typing import Any, Mapping, Optional, Sequence, TypeGuard

from instance_scheduler.model.schedule_definition import (
    ScheduleDefinition,
    ScheduleParams,
    validate_as_schedule_params,
)
from instance_scheduler.model.store.schedule_definition_store import (
    ScheduleAlreadyExistsException,
    ScheduleDefinitionStore,
    UnknownScheduleException,
)
from instance_scheduler.util.validation import ValidationException

SerializedInMemoryScheduleDefinitionStore = Sequence[ScheduleParams]


class InMemoryScheduleDefinitionStore(ScheduleDefinitionStore):
    _data: dict[str, ScheduleDefinition]

    def __init__(self, initial_data: Optional[Mapping[str, ScheduleDefinition]] = None):
        self._data = dict(initial_data) if initial_data else {}

    def put(self, schedule: ScheduleDefinition, overwrite: bool = False) -> None:
        if not overwrite and schedule.name in self._data:
            raise ScheduleAlreadyExistsException(
                f"schedule {schedule.name} already exists"
            )
        self._data[schedule.name] = schedule

    def delete(self, schedule_name: str, error_if_missing: bool = False) -> None:
        if error_if_missing and schedule_name not in self._data:
            raise UnknownScheduleException(f"schedule {schedule_name} does not exist")

        self._data.pop(schedule_name, None)

    def find_by_name(self, schedule_name: str) -> Optional[ScheduleDefinition]:
        return self._data.get(schedule_name, None)

    def find_by_period(self, period_name: str) -> Mapping[str, ScheduleDefinition]:
        def contains_period(sched_def: ScheduleDefinition, period_name: str) -> bool:
            for period_identifier in sched_def.periods:
                if period_identifier.name == period_name:
                    return True
            return False

        schedules = self.find_all()
        return {
            sched_name: sched_def
            for sched_name, sched_def in schedules.items()
            if contains_period(sched_def, period_name)
        }

    def find_all(self) -> Mapping[str, ScheduleDefinition]:
        return self._data

    def serialize(self) -> SerializedInMemoryScheduleDefinitionStore:
        return [
            schedule_def.to_schedule_params() for schedule_def in self._data.values()
        ]

    @classmethod
    def deserialize(
        cls, data: SerializedInMemoryScheduleDefinitionStore
    ) -> "InMemoryScheduleDefinitionStore":
        schedules: dict[str, ScheduleDefinition] = {}
        for period_params in data:
            schedule_def = ScheduleDefinition.from_schedule_params(period_params)
            schedules[schedule_def.name] = schedule_def

        return InMemoryScheduleDefinitionStore(schedules)

    @staticmethod
    def validate_serial_data(
        data: Any,
    ) -> TypeGuard[SerializedInMemoryScheduleDefinitionStore]:
        if not isinstance(data, Sequence):
            raise ValidationException(
                f"Invalid PeriodStore format: must be a sequence of period definitions, received: {type(data)}"
            )

        for params in data:
            if not isinstance(params, dict):
                raise ValidationException(
                    f"Invalid ScheduleStore format: must be a sequence of ScheduleParams, Sequence contains {type(data)}"
                )
            validate_as_schedule_params(params)

        return True
