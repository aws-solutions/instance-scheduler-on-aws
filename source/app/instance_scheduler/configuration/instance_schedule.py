# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, Sequence, TypedDict
from zoneinfo import ZoneInfo

from aws_lambda_powertools import Logger as PowerToolsLogger

from instance_scheduler import configuration
from instance_scheduler.configuration.running_period import RunningPeriod
from instance_scheduler.configuration.running_period_dict_element import (
    RunningPeriodDictElement,
)
from instance_scheduler.schedulers.states import ScheduleState
from instance_scheduler.util.logger import Logger
from instance_scheduler.util.time import is_aware

DEBUG_ACTIVE_PERIOD_IN_SCHEDULE = 'Active period{} in schedule "{}": {}'
DEBUG_NO_RUNNING_PERIODS = 'No running periods at this time found in schedule "{}" for this time, desired state is {}'
DEBUG_OVERRIDE_STATUS = "Schedule override_status value is {}, desired state is {}"
DEBUG_SCHEDULE = "Schedule is {}"
DEBUG_SET_DESIRED_INSTANCE_TYPE = (
    "Current type of instance is {}, desired type is {}, desired state is set to {} to "
    "restart instance with the desired type"
)
DEBUG_STATE_ANY = (
    '"Any" state period found for current time in schedule "{}", desired state is {}'
)
DEBUG_USED_PERIOD = 'Using period "{}" to set the desired state and instance size'
DEBUG_USED_TIME_FOR_SCHEDULE = "Time used to determine desired for instance is {}"


class PeriodWithDesiredState(TypedDict):
    period: RunningPeriod
    instancetype: Optional[str]
    state: ScheduleState


@dataclass
class InstanceSchedule:
    name: str
    timezone: ZoneInfo
    periods: list[RunningPeriodDictElement] = field(default_factory=list)
    override_status: Optional[str] = None
    description: Optional[str] = None
    stop_new_instances: bool = True
    ssm_maintenance_window: Optional[Sequence[str]] = None
    use_maintenance_window: bool = True
    enforced: bool = False
    hibernate: bool = False
    retain_running: bool = False
    configured_in_stack: Optional[str] = None

    def __post_init__(self) -> None:
        self._logger: Optional[Logger | PowerToolsLogger] = None

    def _log_debug(self, msg: str, *args: Optional[str]) -> None:
        if self._logger is not None:
            self._logger.debug(msg, *args)

    def __str__(  # NOSONAR -- (cog-complexity) is just a string-formatting function
        self,
    ) -> str:
        s = 'Schedule "{}": '.format(self.name)
        attributes = []
        if self.description:
            attributes.append(" ({})".format(self.description))
        if self.override_status is not None:
            attributes.append(
                "always {} through override_status".format(
                    "running" if self.override_status else "stopped"
                )
            )
        if self.timezone:
            attributes.append("timezone is {}".format(str(self.timezone)))
        if self.stop_new_instances is not None:
            attributes.append(
                "new instanced are {} stopped".format(
                    "" if self.stop_new_instances else "not "
                )
            )
        if self.ssm_maintenance_window:
            attributes.append(
                "SSM maintenance windows configured for this scheduler are {}".format(
                    self.ssm_maintenance_window
                )
            )
        if self.enforced is not None:
            attributes.append(
                "schedule state is {} enforced to start or stop instances".format(
                    "" if self.enforced else "not "
                )
            )
        if self.hibernate is not None:
            attributes.append(
                "stopped ec2 instances are is {} hibernated when stopped".format(
                    "" if self.hibernate else "not "
                )
            )
        if self.retain_running is not None:
            attributes.append(
                "instances are {} stopped if at the and of a period if they were already running at the start of the period".format(
                    "not" if self.retain_running else ""
                )
            )

        if self.periods and len(self.periods) > 0:
            pl = []
            for p in self.periods:
                ps = "{}".format(str(p["period"].name))
                if "instancetype" in p and p["instancetype"] is not None:
                    ps += ":instancetype {}".format(p["instancetype"])
                pl.append(ps)
            attributes.append("periods: [" + ", ".join(pl) + "]")
        s += "\n".join(attributes)
        return s

    def _localize_time(self, time: datetime) -> datetime:
        if not is_aware(time):
            raise ValueError("Attempted to localize non-timezone-aware datetime")
        return time.astimezone(self.timezone)

    def get_desired_state(
        self,
        dt: datetime,
        logger: Optional[Logger | PowerToolsLogger] = None,
        check_adjacent_periods: bool = True,
    ) -> tuple[ScheduleState, Optional[str], Optional[str]]:
        """
        Test if an instance should be running at a specific moment in this schedule
        :param logger: logger for logging output of scheduling logic
        :param dt: date time to use for scheduling, THIS MUST BE A TIMEZONE-AWARE DATETIME
        :param check_adjacent_periods: check for adjacent periods in a schedule
        :return: desired state, instance type and name of the active period of the schedule if the state is running
        """
        self._logger = logger

        # must localize the scheduling time to the timezone of the schedule
        localized_time = self._localize_time(dt)
        self._log_debug(
            f"Time used to determine desired_state for schedule {self.name}"
            f" is {localized_time.strftime('%c')} {localized_time.tzname()}"
        )
        desired_state, desired_type, period_name = self._get_desired_state_at_time(
            localized_time
        )

        """
        when returning a stopped state, it is possible that we are immediately between 2 adjacent running periods
        (4:00-12:00, 12:01-5:00). In this scenario if we ran at 12:00 we would get a "stopped" state because we are
        at the end of the first period but the second period has not started yet. To overcome this, we check
        1 minute in the past and 1 minute in the future (11:59 and 12:01) and if both checks return a "running"
        state we return the desired state (running) and type of the new period about to be entered,
        """
        if (
            len(self.periods) > 1
            and desired_state == ScheduleState.STOPPED
            and check_adjacent_periods
        ):
            self._log_debug("Checking for adjacent running periods at current time")
            (
                prev_desired_state,
                prev_desired_type,
                prev_period_name,
            ) = self._get_desired_state_at_time(localized_time - timedelta(minutes=1))
            (
                future_desired_state,
                future_desired_type,
                future_period_name,
            ) = self._get_desired_state_at_time(localized_time + timedelta(minutes=1))

            if (
                prev_desired_state == ScheduleState.RUNNING
                and future_desired_state == ScheduleState.RUNNING
            ):
                self._log_debug(
                    "Adjacent periods found, keep instance in running state"
                )
                return future_desired_state, future_desired_type, future_period_name

        return desired_state, desired_type, period_name

    def _get_desired_state_at_time(
        self,
        localized_time: datetime,
    ) -> tuple[ScheduleState, Optional[str], Optional[str]]:
        """
        core logic for determining the desired state of a schedule at a specific instant in time
        :param localized_time: a datetime object that MUST BE LOCALIZED to the schedule's current timezone using
        _localalize_time(). Failure to localize this datetime to the correct timezone will cause incorrect timezone
        behavior
        :return: a tuple of (desired_state, desired_type, period_name) where period_name is the name of the
        "most authoritative" period that determined the other 2 values
        """

        # override_status flag short-circuit override
        if self.override_status:
            desired_state: ScheduleState = (
                ScheduleState.RUNNING
                if self.override_status == configuration.OVERRIDE_STATUS_RUNNING
                else ScheduleState.STOPPED
            )
            self._log_debug(DEBUG_OVERRIDE_STATUS, self.override_status, desired_state)
            return desired_state, None, "override_status"

        # get a list of all period schedules along with their desired states at the specified time
        periods_with_desired_states = self.get_periods_with_desired_states(
            localized_time
        )

        # desired states have a relative priority of running > any > stopped. The desired state of a schedule is
        # the highest priority state of any period within that schedule
        if any(period["state"] == "running" for period in periods_with_desired_states):
            """
            in the event that we have multiple overlapping periods that are all in the "running" state we must pick
            a specific period from which to get the "desired_type" from. This "most_authoritative" period
            is defined as the period that most recently started.

            For example:
            Period1 = 6am-6pm, Period2 = 10am-4pm, CurrentTime = 1pm
            most authoritative period = Period2 because it is the most recent one to have started
            """
            running_periods = [
                period
                for period in periods_with_desired_states
                if period["state"] == "running"
            ]
            current_running_period = get_nearest_running_period(running_periods)
            desired_type: Optional[str] = current_running_period["instancetype"]

            return (
                ScheduleState.RUNNING,
                desired_type,
                current_running_period["period"].name,
            )
        elif any(period["state"] == "any" for period in periods_with_desired_states):
            return ScheduleState.ANY, None, None
        else:
            return ScheduleState.STOPPED, None, None

    def get_periods_with_desired_states(
        self, time: datetime
    ) -> list[PeriodWithDesiredState]:
        periods_with_desired_states: list[PeriodWithDesiredState] = [
            {
                "period": p["period"],
                "instancetype": p.get("instancetype", None),
                "state": p["period"].get_desired_state(self._logger, time),
            }
            for p in self.periods
        ]
        return periods_with_desired_states


def get_nearest_running_period(
    periods: list[PeriodWithDesiredState],
) -> PeriodWithDesiredState:
    """given a list of running periods, get "nearest period" which is defined as
    the running period with the latest start time"""

    if not periods:
        raise ValueError(
            "Tried to find the latest start time of an empty list of periods"
        )

    latest_period = periods[0]
    for period in periods:
        if period["period"].begintime is None:
            continue  # begintime of none cannot possibly be more recent than latest period
        elif latest_period["period"].begintime is None:
            latest_period = period
        elif period["period"].begintime > latest_period["period"].begintime:
            latest_period = period

    return latest_period
