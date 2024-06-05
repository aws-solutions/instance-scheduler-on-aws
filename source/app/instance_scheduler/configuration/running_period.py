# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from dataclasses import dataclass
from datetime import datetime, time
from typing import Literal, Optional

from aws_lambda_powertools import Logger as PowerToolsLogger

from instance_scheduler.cron.cron_recurrence_expression import CronRecurrenceExpression
from instance_scheduler.schedulers.states import ScheduleState
from instance_scheduler.util.display_helper import time_str
from instance_scheduler.util.logger import Logger


class RunningPeriodValidationException(Exception):
    """An error occurred while validating the consistency of a running period"""


@dataclass
class RunningPeriod:
    name: str
    begintime: Optional[time] = None
    endtime: Optional[time] = None
    cron_recurrence: CronRecurrenceExpression = CronRecurrenceExpression()

    def __post_init__(self) -> None:
        self._logger: Optional[Logger | PowerToolsLogger] = None
        self._validate()

    def _validate(self) -> None:
        if self.name is None or self.name == "":
            raise RunningPeriodValidationException(
                "Constraint Violation: name cannot be none or empty"
            )

        if self.begintime and self.endtime and self.begintime > self.endtime:
            raise RunningPeriodValidationException(
                f"Constraint Violation: begintime {self.begintime.strftime('%H:%M')} "
                f"must be before endtime {self.endtime.strftime('%H:%M')}"
            )

    def _log_debug(self, msg: str, *args: str) -> None:
        if self._logger is not None:
            self._logger.debug(msg, *args)

    def get_desired_state(
        self, logger: Optional[Logger | PowerToolsLogger], current_dt: datetime
    ) -> ScheduleState:
        """
        Test if the instance should be running at the specified dt, all conditions configured a period should be true
        :param logger: logger to log the output of scheduling logic
        :param current_dt: time to test
        :return: desired state for the instance in the period
        """
        self._logger = logger
        self._log_debug('Checking conditions for period "{}"', self.name)
        if not self.cron_recurrence.contains(current_dt):
            return ScheduleState.STOPPED
        return self.check_time(current_dt)

    def check_time(self, dt: datetime) -> ScheduleState:
        """
        check the given time against the begin and end times of this period
        :param dt:
        :return:
        """
        time_to_check = time(dt.hour, dt.minute, dt.second)

        # debug msg
        period_type: str

        # no start and stop time, means running all day
        if self.begintime is None and self.endtime is None:
            desired_state: ScheduleState = ScheduleState.RUNNING
            period_type = "all-day"
        elif self.begintime is None and self.endtime is not None:
            # just the end time, stopped if later than that time
            desired_state = (
                ScheduleState.STOPPED
                if time_to_check >= self.endtime
                else ScheduleState.ANY
            )
            period_type = f"1-sided stop ({time_str(self.endtime)})"
        elif self.begintime is not None and self.endtime is None:
            # just the start time, running if later that that time
            desired_state = (
                ScheduleState.RUNNING
                if time_to_check >= self.begintime
                else ScheduleState.ANY
            )
            period_type = f"1-sided start ({time_str(self.begintime)})"
        elif self.begintime is not None and self.endtime is not None:
            # start and stop time, test if time falls in the period defined by these times
            desired_state = (
                ScheduleState.RUNNING
                if self.begintime <= time_to_check < self.endtime
                else ScheduleState.STOPPED
            )
            period_type = f"range ({time_str(self.begintime)}-{time_str(self.endtime)})"
        else:
            assert False, "unreachable"
            # the above defines all 4 possible combinations of none/not_none on begintime and endtime
            # so this should be impossible to reach

        self._log_debug(
            "Period CheckTime Result:\n"
            "  PeriodType: {}\n"
            "  timeChecked: {} ({})\n"
            "  desiredState: {}",
            period_type,
            dt.isoformat(),
            time_str(time_to_check),
            desired_state,
        )
        return desired_state


# string format helpers for debug messages
def _not_str(is_not_not: bool) -> str:
    return "" if is_not_not else "not "


def _state_str(checked: bool) -> Literal["[running]", "[stopped]"]:
    return "[running]" if checked else "[stopped]"


def _check_running_state_str(
    checked_state: str,
) -> Literal["[running]", "[stopped]"]:
    return _state_str(checked_state != "stopped")
