# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from collections.abc import Mapping
from typing import Iterable, Optional

from instance_scheduler.model.schedule_definition import ScheduleDefinition
from instance_scheduler.model.store.dynamo_schedule_definition_store import (
    DynamoScheduleDefinitionStore,
)
from instance_scheduler.model.store.in_memory_schedule_definition_store import (
    InMemoryScheduleDefinitionStore,
)
from instance_scheduler.model.store.schedule_definition_store import (
    ScheduleDefinitionStore,
)


class CachedScheduleDefinitionStore(ScheduleDefinitionStore):
    def __init__(self, table_name: str):
        self._memory_store = InMemoryScheduleDefinitionStore()
        self._dynamo_store = DynamoScheduleDefinitionStore(table_name)

    def put(self, schedule: ScheduleDefinition, overwrite: bool = False) -> None:
        self._dynamo_store.put(schedule, overwrite)
        self._memory_store.put(schedule, overwrite=True)

    def delete(self, schedule_name: str, error_if_missing: bool = False) -> None:
        self._dynamo_store.delete(schedule_name, error_if_missing)
        self._memory_store.delete(schedule_name, error_if_missing=False)

    def find_by_name(
        self, schedule_name: str, cache_only: bool = False
    ) -> Optional[ScheduleDefinition]:
        result = self._memory_store.find_by_name(schedule_name)
        if result is None and not cache_only:
            result = self._dynamo_store.find_by_name(schedule_name)
            if result is not None:
                self._memory_store.put(result, overwrite=True)
        return result

    def find_by_period(
        self, period_name: str, cache_only: bool = False
    ) -> Mapping[str, ScheduleDefinition]:
        if cache_only:
            return self._memory_store.find_by_period(period_name)

        dynamo_results = self._dynamo_store.find_by_period(period_name)
        for name, schedule in dynamo_results.items():
            self._memory_store.put(schedule, overwrite=True)
        return dynamo_results

    def find_all(self, cache_only: bool = False) -> Mapping[str, ScheduleDefinition]:
        if cache_only:
            return self._memory_store.find_all()

        dynamo_results = self._dynamo_store.find_all()
        for name, schedule in dynamo_results.items():
            self._memory_store.put(schedule, overwrite=True)
        return dynamo_results

    def preload_cache(self, schedules: Iterable[ScheduleDefinition]) -> None:
        for schedule in schedules:
            self._memory_store.put(schedule, overwrite=True)
