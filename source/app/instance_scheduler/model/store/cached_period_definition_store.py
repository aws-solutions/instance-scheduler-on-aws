# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from collections.abc import Mapping
from typing import Iterable, Optional

from instance_scheduler.model.period_definition import PeriodDefinition
from instance_scheduler.model.store.dynamo_period_definition_store import (
    DynamoPeriodDefinitionStore,
)
from instance_scheduler.model.store.in_memory_period_definition_store import (
    InMemoryPeriodDefinitionStore,
)
from instance_scheduler.model.store.period_definition_store import PeriodDefinitionStore


class CachedPeriodDefinitionStore(PeriodDefinitionStore):
    def __init__(self, table_name: str):
        self._memory_store = InMemoryPeriodDefinitionStore()
        self._dynamo_store = DynamoPeriodDefinitionStore(table_name)

    def put(self, period: PeriodDefinition, overwrite: bool = False) -> None:
        self._dynamo_store.put(period, overwrite)
        self._memory_store.put(period, overwrite=True)

    def delete(self, period_name: str, error_if_missing: bool = False) -> None:
        self._dynamo_store.delete(period_name, error_if_missing)
        self._memory_store.delete(period_name, error_if_missing=False)

    def find_by_name(
        self, period_name: str, cache_only: bool = False
    ) -> Optional[PeriodDefinition]:
        result = self._memory_store.find_by_name(period_name)
        if result is None and not cache_only:
            result = self._dynamo_store.find_by_name(period_name)
            if result is not None:
                self._memory_store.put(result, overwrite=True)
        return result

    def find_all(self, cache_only: bool = False) -> Mapping[str, PeriodDefinition]:
        if cache_only:
            return self._memory_store.find_all()

        dynamo_results = self._dynamo_store.find_all()
        for name, period in dynamo_results.items():
            self._memory_store.put(period, overwrite=True)
        return dynamo_results

    def preload_cache(self, periods: Iterable[PeriodDefinition]) -> None:
        for period in periods:
            self._memory_store.put(period, overwrite=True)
