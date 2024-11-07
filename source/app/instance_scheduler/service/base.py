# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from abc import ABC, abstractmethod
from collections.abc import Iterator
from typing import Generic, TypeVar

from instance_scheduler.schedulers.states import ScheduleState
from instance_scheduler.service.abstract_instance import AbstractInstance

T = TypeVar("T", bound=AbstractInstance)


class Service(Generic[T], ABC):

    @property
    @abstractmethod
    def service_name(self) -> str:
        pass

    @abstractmethod
    def describe_tagged_instances(self) -> Iterator[T]:
        pass

    @abstractmethod
    def start_instances(
        self, instances_to_start: list[T]
    ) -> Iterator[tuple[T, Exception]]:
        """start a collection of instances

        :returns: a tuple stream of instances that fail to start: (instance, exception)
        """
        pass

    @abstractmethod
    def stop_instances(
        self, instances_to_stop: list[T]
    ) -> Iterator[tuple[str, ScheduleState]]:
        pass

    @abstractmethod
    def resize_instance(self, instance: T, instance_type: str) -> None:
        pass
