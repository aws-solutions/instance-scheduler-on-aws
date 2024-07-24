# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import datetime
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Optional, TypedDict
from zoneinfo import ZoneInfo

from instance_scheduler import configuration
from instance_scheduler.configuration.instance_schedule import InstanceSchedule
from instance_scheduler.util.time import is_aware


class TagTemplate(TypedDict):
    Key: str
    Value: str


@dataclass(frozen=True)
class SchedulingContext:
    account_id: str
    service: str
    region: str
    current_dt: datetime.datetime
    default_timezone: ZoneInfo
    schedules: Mapping[str, InstanceSchedule]
    scheduling_interval_minutes: int
    started_tags: list[TagTemplate] = field(default_factory=list)
    stopped_tags: list[TagTemplate] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not is_aware(self.current_dt):
            raise ValueError(
                f"SchedulingContext datetime must be timezone-Aware. Received: {self.current_dt}"
            )

    def get_schedule(self, name: Optional[str]) -> Optional[InstanceSchedule]:
        """
        Get a schedule by its name
        :param name: name of the schedule
        :return: Schedule, None f it does not exist
        """
        if not name:
            return None
        return self.schedules[name] if name in self.schedules else None


def get_time_from_string(timestr: Optional[str]) -> Optional[datetime.time]:
    """
    Standardised method to build time object instance from time string
    :param timestr: string in format as defined in configuration.TIME_FORMAT_STRING
    :return: time object from time string, None if the time is invalid
    """
    if not timestr:
        return None
    try:
        tm = time.strptime(timestr, configuration.TIME_FORMAT_STRING)
    except ValueError:
        return None
    return datetime.time(tm.tm_hour, tm.tm_min, 0)
