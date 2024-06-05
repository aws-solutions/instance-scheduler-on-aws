# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Optional

from instance_scheduler.model.period_definition import PeriodDefinition


class UnknownPeriodException(Exception):
    pass


class PeriodAlreadyExistsException(Exception):
    pass


class PeriodDefinitionStore(ABC):
    @abstractmethod
    def put(self, period: PeriodDefinition, overwrite: bool = False) -> None:
        raise NotImplementedError()

    @abstractmethod
    def delete(self, period_name: str, error_if_missing: bool = False) -> None:
        raise NotImplementedError()

    @abstractmethod
    def find_by_name(self, period_name: str) -> Optional[PeriodDefinition]:
        raise NotImplementedError()

    @abstractmethod
    def find_all(self) -> Mapping[str, PeriodDefinition]:
        raise NotImplementedError()
