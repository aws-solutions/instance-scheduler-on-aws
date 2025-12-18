# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Iterator, Optional

from instance_scheduler.model.managed_instance import RegisteredInstance, RegistryKey


class ResourceAlreadyRegisteredException(Exception):
    pass


class UnknownResourceException(Exception):
    pass


@dataclass()
class SchedulingTarget:
    account: str
    region: str
    service: str
    resources: list[RegisteredInstance]

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SchedulingTarget):
            return False
        return bool(
            self.account == other.account
            and self.region == other.region
            and self.service == other.service
        )


class ResourceRegistry(ABC):

    @abstractmethod
    def put(self, resource: RegisteredInstance, overwrite: bool = False) -> None:
        raise NotImplementedError()

    @abstractmethod
    def delete(self, key: RegistryKey, error_if_missing: bool = False) -> None:
        raise NotImplementedError()

    @abstractmethod
    def find_all(self) -> Iterator[RegisteredInstance]:
        # defined return order -- PKs arbitrary, SKs in sorted order
        raise NotImplementedError()

    @abstractmethod
    def find_by_scheduling_target(
        self, account: str, region: str, service: str
    ) -> Iterator[RegisteredInstance]:
        raise NotImplementedError()

    @abstractmethod
    def find_by_account(self, account: str) -> Iterator[RegisteredInstance]:
        raise NotImplementedError()

    @abstractmethod
    def get(self, key: RegistryKey) -> RegisteredInstance | None:
        raise NotImplementedError()

    def list_all_by_scheduling_target(self) -> Iterator[SchedulingTarget]:
        # Items are returned by arbitrary Partition (accountID) in sort-key order (resource#{region}#{service}#{id})
        # This allows us to group by target based on the return order
        curr_target: Optional[SchedulingTarget] = None
        for resource in self.find_all():
            target = SchedulingTarget(
                account=resource.account,
                region=resource.region,
                service=resource.service,
                resources=[],
            )

            if target == curr_target:
                curr_target.resources.append(resource)
            else:
                if curr_target:
                    yield curr_target
                curr_target = target
                target.resources = [resource]

        # finally yield the last target if one exists
        if curr_target:
            yield curr_target
