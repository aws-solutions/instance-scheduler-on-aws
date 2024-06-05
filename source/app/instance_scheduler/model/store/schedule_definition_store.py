# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Optional

from instance_scheduler.model.schedule_definition import ScheduleDefinition


class UnknownScheduleException(Exception):
    pass


class ScheduleAlreadyExistsException(Exception):
    pass


class ScheduleDefinitionStore(ABC):
    @abstractmethod
    def put(self, schedule: ScheduleDefinition, overwrite: bool = False) -> None:
        raise NotImplementedError()

    @abstractmethod
    def delete(self, schedule_name: str, error_if_missing: bool = False) -> None:
        raise NotImplementedError()

    @abstractmethod
    def find_by_name(self, schedule_name: str) -> Optional[ScheduleDefinition]:
        raise NotImplementedError()

    @abstractmethod
    def find_by_period(self, period_name: str) -> Mapping[str, ScheduleDefinition]:
        raise NotImplementedError()

    @abstractmethod
    def find_all(self) -> Mapping[str, ScheduleDefinition]:
        raise NotImplementedError()
