# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from typing import Iterable, Iterator

from instance_scheduler.model.managed_instance import RegisteredInstance, RegistryKey
from instance_scheduler.model.store.dynamo_resource_registry import (
    DynamoResourceRegistry,
)
from instance_scheduler.model.store.in_memory_resource_registry import (
    InMemoryResourceRegistry,
)
from instance_scheduler.model.store.resource_registry import ResourceRegistry


class CachedResourceRegistry(ResourceRegistry):
    def __init__(self, table_name: str):
        self._memory_store = InMemoryResourceRegistry()
        self._dynamo_store = DynamoResourceRegistry(table_name)

    def put(self, resource: RegisteredInstance, overwrite: bool = False) -> None:
        self._dynamo_store.put(resource, overwrite)
        self._memory_store.put(resource, overwrite=True)

    def get(
        self, key: RegistryKey, cache_only: bool = False
    ) -> RegisteredInstance | None:
        result = self._memory_store.get(key)
        if result is None and not cache_only:
            result = self._dynamo_store.get(key)
            if result is not None:
                self._memory_store.put(result, overwrite=True)
        return result

    def delete(self, key: RegistryKey, error_if_missing: bool = False) -> None:
        self._dynamo_store.delete(key, error_if_missing)
        self._memory_store.delete(key, error_if_missing=False)

    def find_all(self, cache_only: bool = False) -> Iterator[RegisteredInstance]:
        if cache_only:
            yield from self._memory_store.find_all()
            return

        for resource in self._dynamo_store.find_all():
            self._memory_store.put(resource, overwrite=True)
            yield resource

    def find_by_account(
        self, account: str, cache_only: bool = False
    ) -> Iterator[RegisteredInstance]:
        if cache_only:
            yield from self._memory_store.find_by_account(account)
            return

        for resource in self._dynamo_store.find_by_account(account):
            self._memory_store.put(resource, overwrite=True)
            yield resource

    def find_by_scheduling_target(
        self, account: str, region: str, service: str, cache_only: bool = False
    ) -> Iterator[RegisteredInstance]:
        if cache_only:
            yield from self._memory_store.find_by_scheduling_target(
                account, region, service
            )
            return

        for resource in self._dynamo_store.find_by_scheduling_target(
            account, region, service
        ):
            self._memory_store.put(resource, overwrite=True)
            yield resource

    def preload_cache(self, resources: Iterable[RegisteredInstance]) -> None:
        for resource in resources:
            self._memory_store.put(resource, overwrite=True)
