######################################################################################################################
#  Copyright 2019 Amazon.com, Inc. or its affiliates. All Rights Reserved.                                           #
#                                                                                                                    #
#  Licensed under the Apache License Version 2.0 (the "License"). You may not use this file except in compliance     #
#  with the License. A copy of the License is located at                                                             #
#                                                                                                                    #
#      http://www.apache.org/licenses/                                                                               #
#                                                                                                                    #
#  or in the "license" file accompanying this file. This file is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES #
#  OR CONDITIONS OF ANY KIND, express or implied. See the License for the specific language governing permissions    #
#  and limitations under the License.                                                                                #
######################################################################################################################

import datetime

import configuration
from configuration.instance_schedule import InstanceSchedule
from util.display_helper import set_str, time_str

DEBUG_CHECK_DT_START_TIME = "{} Time {} is {} starttime {}, returned state is {}"
DEBUG_CHECK_DT_START_AND_STOP = "{} Time {} is {} {}-{}, returned state is {}"
DEBUG_CHECK_DT = "Checking conditions for period \"{}\""
DEBUG_CHECK_DT_STOP_TIME = "{} Time {} is {} stoptime {}, returned state is {}"
DEBUG_CHECK_DT_UNDEFINED_START_STOP = "{} No start or stop time, returned state is {}"
DEBUG_CHECK_MONTH = "{} Month \"{}\" {}in months ({})"
DEBUG_CHECK_MONTH_DAY = "{} Day of month {} {}in month days ({})"
DEBUG_CHECK_WEEKDAYS = "{} Weekday \"{}\" {}in weekdays ({})"


class RunningPeriod:
    def __init__(self, name, begintime=None, endtime=None, weekdays=None, months=None, monthdays=None):
        """
        Defines a period in which an instance should be running
        :param name: name of the period
        :param begintime: begin time of the period (time)
        :param endtime: end time of the period (time)
        :param weekdays: weekdays (set 0..6)
        :param months: months of the period (set 1..12)
        :param monthdays: days in the month (set 1..28-31)
        """
        self.name = name
        self.begintime = begintime
        self.endtime = endtime
        self.weekdays = weekdays
        self.months = months
        self.monthdays = monthdays
        self._logger = None

    def __str__(self):
        s = "Period \"{}\": ".format(self.name)
        conditions = []
        if self.begintime:
            conditions.append("starts at {}".format(time_str(self.begintime)))
        if self.endtime:
            conditions.append("ends at {}".format(time_str(self.endtime)))
        if self.weekdays is not None:
            conditions.append("on weekdays ({})".format(set_str(self.weekdays, configuration.WEEKDAY_NAMES)))
        if self.monthdays:
            conditions.append("on monthdays ({})".format(set_str(self.monthdays)))
        if self.months:
            conditions.append("in months ({})".format(set_str(self.months, configuration.MONTH_NAMES, offset=1)))
        s += ", ".join(conditions)

        return s

    def _log_debug(self, msg, *args):
        if self._logger is not None:
            self._logger.debug(msg, *args)

    def _log_info(self, msg, *args):
        if self._logger is not None:
            self._logger.info(msg, *args)

    def get_desired_state(self, logger, current_dt):
        """
        Test if the instance should be running at the specified dt, all conditions configured a period should be true
        :param logger: logger to log the output of scheduling logic
        :param current_dt: time to test
        :return: desired state for the instance in the period
        """

        def state_str(checked):
            return "[running]" if checked else "[stopped]"

        def check_running_state_str(checked_state):
            return state_str(checked_state != InstanceSchedule.STATE_STOPPED)

        def not_str(is_not_not):
            return "" if is_not_not else "not "

        # check day of month
        def check_monthday(dt):
            result = self.monthdays is None or dt.day in self.monthdays
            if self.monthdays:
                self._log_debug(DEBUG_CHECK_MONTH_DAY, state_str(result), dt.day, "" if result else "not ", set_str(self.monthdays))
            return result

        # check month
        def check_month(dt):
            result = self.months is None or dt.month in self.months
            if self.months:
                self._log_debug(DEBUG_CHECK_MONTH, state_str(result), configuration.MONTH_NAMES[dt.month - 1], not_str(result),
                                set_str(self.months, displaynames=configuration.MONTH_NAMES, offset=1))
            return result

        # check weekday
        def check_weekday(dt):
            result = self.weekdays is None or dt.weekday() in self.weekdays
            if self.weekdays is not None:
                self._log_debug(DEBUG_CHECK_WEEKDAYS, state_str(result), configuration.WEEKDAY_NAMES[dt.weekday()], not_str(result),
                                set_str(self.weekdays, displaynames=configuration.WEEKDAY_NAMES))
            return result

        # check time
        def check_time(dt):

            t = datetime.time(dt.hour, dt.minute, dt.second)
            ts = time_str(t)

            # no start and stop time, means running all day
            if self.begintime is None and self.endtime is None:
                desired_state = InstanceSchedule.STATE_RUNNING
                self._log_debug(DEBUG_CHECK_DT_UNDEFINED_START_STOP, state_str(True), desired_state)
                return desired_state
            elif self.begintime is None:
                # just the end time, stopped if later than that time
                desired_state = InstanceSchedule.STATE_STOPPED if t >= self.endtime else InstanceSchedule.STATE_ANY
                self._log_debug(DEBUG_CHECK_DT_STOP_TIME,
                                check_running_state_str(desired_state), ts,
                                "before" if desired_state == InstanceSchedule.STATE_ANY else "after",
                                time_str(self.endtime), desired_state)
                return desired_state

            elif self.begintime is not None and self.endtime is None:
                # just the start time, running if later that that time
                desired_state = InstanceSchedule.STATE_RUNNING if t >= self.begintime else InstanceSchedule.STATE_ANY
                self._log_debug(DEBUG_CHECK_DT_START_TIME,
                                check_running_state_str(desired_state), ts,
                                "before" if desired_state == InstanceSchedule.STATE_ANY else "after",
                                time_str(self.begintime), desired_state)
                return desired_state
            else:
                # start and stop time, test if time falls in the period defined by these times
                desired_state = InstanceSchedule.STATE_RUNNING \
                    if self.begintime <= t < self.endtime else InstanceSchedule.STATE_STOPPED

                self._log_debug(DEBUG_CHECK_DT_START_AND_STOP,
                                check_running_state_str(desired_state), ts,
                                "within" if desired_state == InstanceSchedule.STATE_RUNNING
                                else "outside",
                                time_str(self.begintime), time_str(self.endtime), desired_state)

            return desired_state

        self._logger = logger

        state = InstanceSchedule.STATE_STOPPED

        self._log_debug(DEBUG_CHECK_DT, self.name)
        for check in [check_weekday, check_month, check_monthday]:
            if not check(current_dt):
                return state

        state = check_time(current_dt)
        return state
