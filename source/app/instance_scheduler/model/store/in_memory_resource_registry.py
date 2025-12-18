# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from typing import Iterator, Mapping, Optional

from instance_scheduler.model.managed_instance import RegisteredInstance, RegistryKey
from instance_scheduler.model.store.resource_registry import (
    ResourceAlreadyRegisteredException,
    ResourceRegistry,
    UnknownResourceException,
)


class InMemoryResourceRegistry(ResourceRegistry):
    _data: dict[str, dict[str, RegisteredInstance]]

    def __init__(self, initial_data: Optional[Mapping[str, RegisteredInstance]] = None):
        self._data = {}
        if initial_data:
            for resource in initial_data.values():
                self.put(resource, overwrite=True)

    def put(self, resource: RegisteredInstance, overwrite: bool = False) -> None:
        account = resource.account
        sort_key = resource.key.sort_key

        if account not in self._data:
            self._data[account] = {}

        if not overwrite and sort_key in self._data[account]:
            raise ResourceAlreadyRegisteredException(
                f"resource '{resource.display_name}' already exists"
            )
        self._data[account][sort_key] = resource

    def get(self, key: RegistryKey) -> RegisteredInstance | None:
        account_data = self._data.get(key.account)
        return account_data.get(key.sort_key) if account_data else None

    def delete(self, key: RegistryKey, error_if_missing: bool = False) -> None:
        account_data = self._data.get(key.account)
        if not account_data or key.sort_key not in account_data:
            if error_if_missing:
                raise UnknownResourceException(f"resource ({key}) does not exist")
            return
        account_data.pop(key.sort_key)
        if not account_data:
            self._data.pop(key.account)

    def find_all(self) -> Iterator[RegisteredInstance]:
        for account_data in self._data.values():
            for sort_key in sorted(account_data.keys()):
                yield account_data[sort_key]

    def find_by_account(self, account: str) -> Iterator[RegisteredInstance]:
        account_data = self._data.get(account, {})
        for sort_key in sorted(account_data.keys()):
            yield account_data[sort_key]

    def find_by_scheduling_target(
        self, account: str, region: str, service: str
    ) -> Iterator[RegisteredInstance]:
        prefix = f"resource#{region}#{service}#"
        account_data = self._data.get(account, {})
        matching_keys = [k for k in account_data.keys() if k.startswith(prefix)]
        for sort_key in sorted(matching_keys):
            yield account_data[sort_key]
