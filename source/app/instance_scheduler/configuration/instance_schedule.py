# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, ClassVar, Optional, TypedDict
from zoneinfo import ZoneInfo

from typing_extensions import NotRequired

from instance_scheduler import ScheduleState, configuration
from instance_scheduler.configuration.running_period import RunningPeriod
from instance_scheduler.configuration.running_period_dict_element import (
    RunningPeriodDictElement,
)
from instance_scheduler.util.logger import Logger

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


class Instance(TypedDict):
    id: str
    arn: NotRequired[str]
    allow_resize: bool
    hibernate: bool
    state: Any
    state_name: str
    is_running: bool
    is_terminated: bool
    current_state: ScheduleState
    instancetype: str
    engine_type: NotRequired[str]
    maintenance_window: Optional["InstanceSchedule"]
    tags: dict[str, str]
    name: str
    schedule_name: Optional[str]
    is_cluster: NotRequired[bool]
    resized: NotRequired[bool]
    account: NotRequired[str]
    region: NotRequired[str]
    service: NotRequired[str]
    instance_str: NotRequired[str]


class PeriodWithDesiredState(TypedDict):
    period: RunningPeriod
    instancetype: Optional[str]
    state: ScheduleState


@dataclass
class InstanceSchedule:
    STATE_UNKNOWN: ClassVar[str] = "unknown"
    STATE_ANY: ClassVar[str] = "any"
    STATE_STOPPED: ClassVar[str] = "stopped"
    STATE_STOPPED_FOR_RESIZE: ClassVar[str] = "stopped_for_resize"
    STATE_RUNNING: ClassVar[str] = "running"
    STATE_RETAIN_RUNNING: ClassVar[str] = "retain-running"

    # todo: reduce the number of optionals here, it complicates all downstream dependencies
    name: str
    periods: list[RunningPeriodDictElement] = field(default_factory=list)
    # todo: UTC was defined as the default in the original comments but we need to confirm
    #  exactly how default tz is loaded from cfn input parameters, test it, and then decide if we should remove this
    #  fallback entirely
    timezone: str = "UTC"
    override_status: Optional[str] = None
    description: Optional[str] = None
    use_metrics: Optional[bool] = None
    stop_new_instances: Optional[bool] = None
    use_maintenance_window: Optional[bool] = False
    ssm_maintenance_window: Optional[str] = None
    enforced: Optional[bool] = False
    hibernate: Optional[bool] = False
    retain_running: Optional[bool] = False
    # todo: this value is loaded in global_config but is not respected by scheduling_context.
    #  when these are unified, this may be a behavioral change to consider
    configured_in_stack: Optional[str] = None

    def __post_init__(self) -> None:
        self._logger: Optional[Logger] = None

    def _log_debug(self, msg: str, *args: Optional[str]) -> None:
        if self._logger is not None:
            self._logger.debug(msg, *args)

    def __str__(self) -> str:
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
        if self.use_maintenance_window is not None:
            attributes.append(
                "maintenance windows are {} used to start instances".format(
                    "" if self.use_maintenance_window else "not "
                )
            )
        if self.ssm_maintenance_window is not None and self.use_maintenance_window:
            attributes.append(
                "SSM maintenance window is {} used to start EC2 instances".format(
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

    def get_desired_state(
        self,
        instance: Instance,
        dt: datetime,
        logger: Optional[Logger] = None,
        check_adjacent_periods: bool = True,
    ) -> tuple[ScheduleState, Optional[str], Optional[str]]:
        """
        Test if an instance should be running at a specific moment in this schedule
        :param instance: the instance to test
        :param logger: logger for logging output of scheduling logic
        :param dt: date time to use for scheduling, THIS MUST BE A TIMEZONE-AWARE DATETIME
        :param check_adjacent_periods: check for adjacent periods in a schedule
        :return: desired state, instance type and name of the active period of the schedule if the state is running
        """

        # gets the local time using the configured timezone
        def get_check_time(time: datetime) -> datetime:
            return time.astimezone(ZoneInfo(self.timezone))

        # actions for desired state is running
        def handle_running_state(
            inst: Instance, periods: list[PeriodWithDesiredState]
        ) -> tuple[ScheduleState, Optional[str], str]:
            # used to determining most nearest period if more than one period returns a running state in a schedule
            def latest_starttime(
                p1: PeriodWithDesiredState, p2: PeriodWithDesiredState
            ) -> PeriodWithDesiredState:
                if p1["period"].begintime is None:
                    return p2
                if p2["period"].begintime is None:
                    return p1
                return p1 if p1["period"].begintime > p2["period"].begintime else p2

            # test if we need to change the type of the instance
            def requires_adjust_instance_size(
                desired_instance_type: Optional[str], checked_instance: Instance
            ) -> bool:
                return (
                    checked_instance["allow_resize"]
                    and desired_instance_type is not None
                    and checked_instance["is_running"]
                    and desired_instance_type != checked_instance["instancetype"]
                )

            # reduce is removed from python3, replace by minimal implementation for python3 compatibility
            def _reduce(
                fn: Callable[
                    [PeriodWithDesiredState, PeriodWithDesiredState],
                    PeriodWithDesiredState,
                ],
                items: list[PeriodWithDesiredState],
            ) -> Optional[PeriodWithDesiredState]:
                if items is None or len(list(items)) == 0:
                    return None
                else:
                    result = items[0]
                    i = 1
                    while i < len(items):
                        result = fn(result, items[i])
                        i += 1
                    return result

            # nearest period in schedule with running state
            current_running_period = _reduce(latest_starttime, periods)

            if not current_running_period:
                raise ValueError(
                    "Tried to find the latest start time of an empty list of periods"
                )

            multiple_active_periods = len(list(periods)) > 1

            self._log_debug(
                DEBUG_ACTIVE_PERIOD_IN_SCHEDULE.format(
                    "s" if multiple_active_periods else "",
                    self.name,
                    ",".join('"' + per["period"].name + '"' for per in periods),
                )
            )
            if multiple_active_periods:
                self._log_debug(
                    DEBUG_USED_PERIOD.format(current_running_period["period"].name)
                )

            desired_state: ScheduleState = "running"
            desired_type: Optional[str] = (
                current_running_period["instancetype"] if inst["allow_resize"] else None
            )

            # check if the instance type matches the desired type, if not set the status to stopped if the instance is currently
            # and the instance will be started with the desired type at the next invocation
            if requires_adjust_instance_size(desired_type, inst):
                desired_state = "stopped_for_resize"
                self._log_debug(
                    DEBUG_SET_DESIRED_INSTANCE_TYPE,
                    inst["instancetype"],
                    desired_type,
                    desired_state,
                )
            return desired_state, desired_type, current_running_period["period"].name

        # actions for desired state is any state
        def handle_any_state() -> tuple[ScheduleState, None, None]:
            desired_state: ScheduleState = "any"
            self._log_debug(DEBUG_STATE_ANY, self.name, desired_state)
            return desired_state, None, None

        # actions for desired state is stopped
        def handle_stopped_state() -> tuple[ScheduleState, None, None]:
            desired_state: ScheduleState = "stopped"
            self._log_debug(DEBUG_NO_RUNNING_PERIODS, self.name, desired_state)
            return desired_state, None, None

        # actions if there is an override value set for the schema
        def handle_override_status() -> tuple[ScheduleState, None, str]:
            desired_state: ScheduleState = (
                "running"
                if self.override_status == configuration.OVERRIDE_STATUS_RUNNING
                else "stopped"
            )
            self._log_debug(DEBUG_OVERRIDE_STATUS, self.override_status, desired_state)
            return desired_state, None, "override_status"

        self._logger = logger

        # always on or off
        if self.override_status is not None:
            return handle_override_status()

        # test if time is withing any period of the schedule
        localized_time = get_check_time(dt)

        self._log_debug(DEBUG_USED_TIME_FOR_SCHEDULE, localized_time.strftime("%c"))

        # get the desired state for every period in the schedule
        periods_with_desired_states = self.get_periods_with_desired_states(
            localized_time
        )

        # get periods from the schema that have a running state
        periods_with_running_state = [
            p for p in periods_with_desired_states if p["state"] == "running"
        ]

        if any(periods_with_running_state):
            return handle_running_state(instance, periods_with_running_state)

        period_with_any_state = filter(
            lambda period: period["state"] == "any",
            periods_with_desired_states,
        )
        if any(period_with_any_state):
            return handle_any_state()

        if len(periods_with_desired_states) > 1 and check_adjacent_periods:
            self._log_debug("Checking for adjacent running periods at current time")
            self._log_debug("Checking states for previous minute")
            last_minute_running_periods = [
                p
                for p in self.get_periods_with_desired_states(
                    localized_time - timedelta(minutes=1)
                )
                if p["state"] == "running"
            ]
            self._log_debug(
                "Running period(s) for previous minute {}",
                ",".join([p["period"].name for p in last_minute_running_periods]),
            )
            if len(last_minute_running_periods) > 0:
                self._log_debug("Checking states for next minute")
                next_minute_running_periods = [
                    p
                    for p in self.get_periods_with_desired_states(
                        localized_time + timedelta(minutes=1)
                    )
                    if p["state"] == "running"
                ]
                self._log_debug(
                    "Running period(s) for next minute {}",
                    ",".join([p["period"].name for p in next_minute_running_periods]),
                )
                if len(next_minute_running_periods):
                    self._log_debug(
                        "Adjacent periods found, keep instance in running state"
                    )
                    return handle_running_state(instance, last_minute_running_periods)

        return handle_stopped_state()

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
