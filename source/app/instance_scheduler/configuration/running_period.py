# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from dataclasses import dataclass
from datetime import datetime, time
from typing import Literal, Optional

from instance_scheduler import ScheduleState, configuration
from instance_scheduler.util.display_helper import set_str, time_str
from instance_scheduler.util.logger import Logger

DEBUG_CHECK_DT_START_TIME = "{} Time {} is {} starttime {}, returned state is {}"
DEBUG_CHECK_DT_START_AND_STOP = "{} Time {} is {} {}-{}, returned state is {}"
DEBUG_CHECK_DT = 'Checking conditions for period "{}"'
DEBUG_CHECK_DT_STOP_TIME = "{} Time {} is {} stoptime {}, returned state is {}"
DEBUG_CHECK_DT_UNDEFINED_START_STOP = "{} No start or stop time, returned state is {}"
DEBUG_CHECK_MONTH = '{} Month "{}" {}in months ({})'
DEBUG_CHECK_MONTH_DAY = "{} Day of month {} {}in month days ({})"
DEBUG_CHECK_WEEKDAYS = '{} Weekday "{}" {}in weekdays ({})'


@dataclass
class RunningPeriod:
    name: str
    begintime: Optional[time] = None
    endtime: Optional[time] = None
    weekdays: Optional[set[int]] = None
    months: Optional[set[int]] = None
    monthdays: Optional[set[int]] = None

    def __post_init__(self) -> None:
        self._logger: Optional[Logger] = None

    def __str__(self) -> str:
        s = 'Period "{}": '.format(self.name)
        conditions = []
        if self.begintime:
            conditions.append("starts at {}".format(time_str(self.begintime)))
        if self.endtime:
            conditions.append("ends at {}".format(time_str(self.endtime)))
        if self.weekdays is not None:
            conditions.append(
                "on weekdays ({})".format(
                    set_str(self.weekdays, configuration.WEEKDAY_NAMES)
                )
            )
        if self.monthdays:
            conditions.append("on monthdays ({})".format(set_str(self.monthdays)))
        if self.months:
            conditions.append(
                "in months ({})".format(
                    set_str(self.months, configuration.MONTH_NAMES, offset=1)
                )
            )
        s += ", ".join(conditions)

        return s

    def _log_debug(self, msg: str, *args: str) -> None:
        if self._logger is not None:
            self._logger.debug(msg, *args)

    def get_desired_state(
        self, logger: Optional[Logger], current_dt: datetime
    ) -> ScheduleState:
        """
        Test if the instance should be running at the specified dt, all conditions configured a period should be true
        :param logger: logger to log the output of scheduling logic
        :param current_dt: time to test
        :return: desired state for the instance in the period
        """

        def state_str(checked: bool) -> Literal["[running]", "[stopped]"]:
            return "[running]" if checked else "[stopped]"

        def check_running_state_str(
            checked_state: str,
        ) -> Literal["[running]", "[stopped]"]:
            return state_str(checked_state != "stopped")

        def not_str(is_not_not: bool) -> str:
            return "" if is_not_not else "not "

        # check day of month
        def check_monthday(dt: datetime) -> bool:
            result = self.monthdays is None or dt.day in self.monthdays
            if self.monthdays:
                self._log_debug(
                    DEBUG_CHECK_MONTH_DAY,
                    state_str(result),
                    str(dt.day),
                    "" if result else "not ",
                    set_str(self.monthdays),
                )
            return result

        # check month
        def check_month(dt: datetime) -> bool:
            result = self.months is None or dt.month in self.months
            if self.months:
                self._log_debug(
                    DEBUG_CHECK_MONTH,
                    state_str(result),
                    configuration.MONTH_NAMES[dt.month - 1],
                    not_str(result),
                    set_str(
                        self.months, displaynames=configuration.MONTH_NAMES, offset=1
                    ),
                )
            return result

        # check weekday
        def check_weekday(dt: datetime) -> bool:
            result = self.weekdays is None or dt.weekday() in self.weekdays
            if self.weekdays is not None:
                self._log_debug(
                    DEBUG_CHECK_WEEKDAYS,
                    state_str(result),
                    configuration.WEEKDAY_NAMES[dt.weekday()],
                    not_str(result),
                    set_str(self.weekdays, displaynames=configuration.WEEKDAY_NAMES),
                )
            return result

        # check time
        def check_time(dt: datetime) -> ScheduleState:
            t = time(dt.hour, dt.minute, dt.second)
            ts = time_str(t)

            # no start and stop time, means running all day
            if self.begintime is None and self.endtime is None:
                desired_state: ScheduleState = "running"
                self._log_debug(
                    DEBUG_CHECK_DT_UNDEFINED_START_STOP, state_str(True), desired_state
                )
                return desired_state
            elif self.begintime is None and self.endtime is not None:
                # just the end time, stopped if later than that time
                desired_state = "stopped" if t >= self.endtime else "any"
                self._log_debug(
                    DEBUG_CHECK_DT_STOP_TIME,
                    check_running_state_str(desired_state),
                    ts,
                    "before" if desired_state == "any" else "after",
                    time_str(self.endtime),
                    desired_state,
                )
                return desired_state

            elif self.begintime is not None and self.endtime is None:
                # just the start time, running if later that that time
                desired_state = "running" if t >= self.begintime else "any"
                self._log_debug(
                    DEBUG_CHECK_DT_START_TIME,
                    check_running_state_str(desired_state),
                    ts,
                    "before" if desired_state == "any" else "after",
                    time_str(self.begintime),
                    desired_state,
                )
                return desired_state
            elif self.begintime is not None and self.endtime is not None:
                # start and stop time, test if time falls in the period defined by these times
                desired_state = (
                    "running" if self.begintime <= t < self.endtime else "stopped"
                )

                self._log_debug(
                    DEBUG_CHECK_DT_START_AND_STOP,
                    check_running_state_str(desired_state),
                    ts,
                    "within" if desired_state == "running" else "outside",
                    time_str(self.begintime),
                    time_str(self.endtime),
                    desired_state,
                )
            else:
                assert False, "unreachable"
                # the above defines all 4 possible combinations of none/not_none on begintime and endtime
                # so this should be impossible to reach

            return desired_state

        self._logger = logger

        state: ScheduleState = "stopped"

        self._log_debug(DEBUG_CHECK_DT, self.name)
        for check in [check_weekday, check_month, check_monthday]:
            if not check(current_dt):
                return state

        state = check_time(current_dt)
        return state
