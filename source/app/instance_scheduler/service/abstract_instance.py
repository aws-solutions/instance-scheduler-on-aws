# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Sequence

from instance_scheduler.configuration.instance_schedule import InstanceSchedule


@dataclass(kw_only=True)
class AbstractInstance(ABC):
    _id: str
    _name: str
    _schedule_name: str
    _current_state: str
    _instance_type: str
    _tags: dict[str, str]
    _maintenance_windows: Sequence[InstanceSchedule]

    # mutable leftovers from original resizing/hibernate design of EC2, should probably be refactored
    resized: bool = False
    should_hibernate: bool = False

    @property
    def id(self) -> str:
        return self._id

    @property
    def name(self) -> str:
        return self._name

    @property
    def schedule_name(self) -> str:
        return self._schedule_name

    @property
    def current_state(self) -> str:
        return self._current_state

    @property
    def tags(self) -> dict[str, str]:
        return self._tags

    @property
    def instance_type(self) -> str:
        return self._instance_type

    @property
    def maintenance_windows(self) -> Sequence[InstanceSchedule]:
        return self._maintenance_windows

    @property
    @abstractmethod
    def display_str(self) -> str:
        pass

    @property
    @abstractmethod
    def is_schedulable(self) -> bool:
        pass

    @property
    @abstractmethod
    def is_running(self) -> bool:
        pass

    @property
    @abstractmethod
    def is_stopped(self) -> bool:
        pass

    @property
    @abstractmethod
    def is_resizable(self) -> bool:
        pass
