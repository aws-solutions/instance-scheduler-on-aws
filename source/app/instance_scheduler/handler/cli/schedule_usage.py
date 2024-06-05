# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import json
from datetime import datetime, timedelta
from typing import Any, Optional

from instance_scheduler.configuration.instance_schedule import InstanceSchedule
from instance_scheduler.schedulers.states import InstanceState, ScheduleState
from instance_scheduler.util.logger import Logger


def get_schedule_usage(
    schedule: InstanceSchedule,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
) -> Any:
    if not start:
        start = datetime.now(schedule.timezone)
    if not end:
        end = start

    if start > end:
        raise ValueError("stop_date must be equal or later than start_date")

    start = start.replace(tzinfo=schedule.timezone)
    end = end.replace(tzinfo=schedule.timezone)

    return _for_output(
        calculate_schedule_usage_for_period(schedule, start_dt=start, stop_dt=end)
    )


def calculate_schedule_usage_for_period(  # NOSONAR -- (cog-complexity) Deferred - requires an algorithmic rewrite,
    # not just cleanup. preferably using simulation of actual schedule code rather than estimation
    schedule: InstanceSchedule,
    start_dt: datetime,
    stop_dt: Optional[datetime] = None,
    logger: Optional[Logger] = None,
) -> dict[str, Any]:
    result = {}

    stop = stop_dt or start_dt
    if start_dt > stop:
        raise ValueError("stop_date must be equal or later than start_date")

    dt = (
        start_dt
        if isinstance(start_dt, datetime)
        else datetime(start_dt.year, start_dt.month, start_dt.day)
    )
    dt = dt.replace(tzinfo=schedule.timezone)

    while dt <= stop:
        timeline = {dt.replace(hour=0, minute=0)}
        for p in schedule.periods:
            begintime = p["period"].begintime
            endtime = p["period"].endtime
            if begintime is None and endtime is None:
                timeline.add(dt.replace(hour=0, minute=0))
                timeline.add(dt.replace(hour=23, minute=59))
            else:
                if begintime:
                    timeline.add(
                        dt.replace(hour=begintime.hour, minute=begintime.minute)
                    )
                if endtime:
                    timeline.add(dt.replace(hour=endtime.hour, minute=endtime.minute))

        running_periods = {}
        started = None
        starting_period = None
        current_state: InstanceState = InstanceState.UNKNOWN
        for tm in sorted(list(timeline)):
            desired_state, _, period = schedule.get_desired_state(tm, logger, False)

            if current_state != desired_state:  # type: ignore[comparison-overlap]
                if desired_state == ScheduleState.RUNNING:
                    started = tm
                    current_state = InstanceState.RUNNING
                    starting_period = period
                elif desired_state == ScheduleState.STOPPED:
                    stopped = tm
                    (
                        desired_state_with_adj_check,
                        __,
                        ___,
                    ) = schedule.get_desired_state(tm, logger, True)
                    if desired_state_with_adj_check == ScheduleState.RUNNING:
                        stopped += timedelta(minutes=1)
                    if current_state == InstanceState.RUNNING:
                        current_state = InstanceState.STOPPED
                        running_periods[starting_period] = _make_period(
                            started, stopped
                        )

        if current_state == InstanceState.RUNNING:
            stopped = dt.replace(hour=23, minute=59) + timedelta(minutes=1)
            running_periods[starting_period] = _make_period(started, stopped)

        result[str(dt.date())] = {
            "running_periods": running_periods,
            "billing_seconds": sum(
                [running_periods[ps]["billing_seconds"] for ps in running_periods]
            ),
            "billing_hours": sum(
                [running_periods[ph]["billing_hours"] for ph in running_periods]
            ),
        }

        dt += timedelta(days=1)

    return {"schedule": schedule.name, "usage": result}


def _running_seconds(startdt: datetime, stopdt: datetime) -> int:
    return max(int((stopdt - startdt).total_seconds()), 60)


def _running_hours(startdt: datetime, stopdt: datetime) -> int:
    return int(((stopdt - startdt).total_seconds() - 1) / 3600) + 1


def _make_period(started_dt: Any, stopped_dt: Any) -> dict[str, Any]:
    running_period = {
        "begin": started_dt,
        "end": stopped_dt,
        "billing_hours": _running_hours(started_dt, stopped_dt),
        "billing_seconds": _running_seconds(started_dt, stopped_dt),
    }
    return running_period


class CliCustomEncoder(json.JSONEncoder):
    """
    Custom encoding to handle unsupported data types
    """

    def default(self, o: Any) -> Any:
        if isinstance(o, set):
            return list(o)
        if isinstance(o, datetime):
            return o.replace(second=0).strftime("%x %X")

        return json.JSONEncoder.default(self, o)


def _for_output(item: Any) -> Any:
    # to anf from json using custom encoder to convert datetime and set type data into string and lists
    return json.loads(json.dumps(item, cls=CliCustomEncoder))
