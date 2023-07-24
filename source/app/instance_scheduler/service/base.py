# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from abc import ABC, abstractmethod
from collections.abc import Iterator
from typing import Generic, TypedDict, TypeVar

from boto3.session import Session

from instance_scheduler import ScheduleState
from instance_scheduler.configuration.instance_schedule import Instance
from instance_scheduler.configuration.scheduling_context import SchedulingContext
from instance_scheduler.util.logger import Logger


class ServiceArgs(TypedDict):
    account_id: str
    logger: Logger
    stack_name: str
    session: Session
    scheduling_context: SchedulingContext


T = TypeVar("T", bound=Instance)


class Service(Generic[T], ABC):
    def __init__(self, _: ServiceArgs) -> None:
        """noop"""

    @property
    @abstractmethod
    def service_name(self) -> str:
        pass

    @property
    @abstractmethod
    def allow_resize(self) -> bool:
        pass

    @abstractmethod
    def get_schedulable_instances(self) -> list[T]:
        pass

    @abstractmethod
    def start_instances(
        self, instances_to_start: list[T]
    ) -> Iterator[tuple[str, ScheduleState]]:
        pass

    @abstractmethod
    def stop_instances(
        self, instances_to_stop: list[T]
    ) -> Iterator[tuple[str, ScheduleState]]:
        pass

    @abstractmethod
    def resize_instance(self, instance: T, instance_type: str) -> None:
        pass
