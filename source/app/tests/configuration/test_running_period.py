# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import calendar
from datetime import datetime, time

import pytest

from instance_scheduler.configuration.running_period import RunningPeriod
from instance_scheduler.cron.cron_recurrence_expression import CronRecurrenceExpression
from instance_scheduler.cron.parser import (
    parse_monthdays_expr,
    parse_months_expr,
    parse_weekdays_expr,
)
from instance_scheduler.schedulers.states import ScheduleState
from tests.integration.helpers.schedule_helpers import quick_time
from tests.logger import MockLogger


@pytest.mark.parametrize(
    "at_time,expected",
    [
        (quick_time(5, 0, 0), ScheduleState.ANY),
        (quick_time(10, 0, 0), ScheduleState.RUNNING),
        (quick_time(15, 0, 0), ScheduleState.RUNNING),
    ],
)
def test_one_sided_start(at_time: datetime, expected: ScheduleState) -> None:
    period = RunningPeriod(name="test-period", begintime=time(10, 0, 0))
    assert period.get_desired_state(MockLogger(), at_time) == expected


@pytest.mark.parametrize(
    "at_time,expected",
    [
        (quick_time(5, 0, 0), ScheduleState.ANY),
        (quick_time(10, 0, 0), ScheduleState.STOPPED),
        (quick_time(15, 0, 0), ScheduleState.STOPPED),
    ],
)
def test_one_sided_stop(at_time: datetime, expected: ScheduleState) -> None:
    period = RunningPeriod(name="test-period", endtime=time(10, 0, 0))
    assert period.get_desired_state(MockLogger(), at_time) == expected


@pytest.mark.parametrize(
    "at_time,expected",
    [
        (quick_time(5, 0, 0), ScheduleState.STOPPED),
        (quick_time(10, 0, 0), ScheduleState.RUNNING),
        (quick_time(15, 0, 0), ScheduleState.RUNNING),
        (quick_time(20, 0, 0), ScheduleState.STOPPED),
        (quick_time(22, 0, 0), ScheduleState.STOPPED),
    ],
)
def test_regular_period(at_time: datetime, expected: ScheduleState) -> None:
    period = RunningPeriod(
        name="test-period", begintime=time(10, 0, 0), endtime=time(20, 0, 0)
    )
    assert period.get_desired_state(MockLogger(), at_time) == expected


def test_weekdays_only_is_running_on_specified_days() -> None:
    period = RunningPeriod(
        name="name",
        cron_recurrence=CronRecurrenceExpression(
            weekdays=parse_weekdays_expr({"0", "3", "5"})
        ),
    )
    # monday (0)
    assert (
        period.get_desired_state(MockLogger(), datetime(year=2023, month=7, day=10))
        == "running"
    )
    # tuesday (1)
    assert (
        period.get_desired_state(MockLogger(), datetime(year=2023, month=7, day=11))
        == "stopped"
    )
    # wednesday (2)
    assert (
        period.get_desired_state(MockLogger(), datetime(year=2023, month=7, day=12))
        == "stopped"
    )
    # thursday (3)
    assert (
        period.get_desired_state(MockLogger(), datetime(year=2023, month=7, day=13))
        == "running"
    )
    # friday (4)
    assert (
        period.get_desired_state(MockLogger(), datetime(year=2023, month=7, day=14))
        == "stopped"
    )
    # saturday (5)
    assert (
        period.get_desired_state(MockLogger(), datetime(year=2023, month=7, day=15))
        == "running"
    )
    # sunday (6)
    assert (
        period.get_desired_state(MockLogger(), datetime(year=2023, month=7, day=16))
        == "stopped"
    )


def test_month_only_is_running_for_whole_month() -> None:
    period = RunningPeriod(
        name="name",
        cron_recurrence=CronRecurrenceExpression(months=parse_months_expr({"4"})),
    )

    _, days_in_month = calendar.monthrange(year=2023, month=4)
    for month_day in range(1, days_in_month + 1):
        assert (
            period.get_desired_state(
                MockLogger(), datetime(year=2023, month=4, day=month_day)
            )
            == "running"
        ), f"failed for {month_day}"


def test_month_only_is_stopped_in_other_months() -> None:
    period = RunningPeriod(
        name="name",
        cron_recurrence=CronRecurrenceExpression(months=parse_months_expr({"4"})),
    )

    for month in range(1, 13):
        if month == 4:
            continue
        assert (
            period.get_desired_state(
                MockLogger(), datetime(year=2023, month=month, day=3)
            )
            == "stopped"
        ), f"failed for {month}"


def test_monthday_only_is_running_on_specific_monthdays() -> None:
    period = RunningPeriod(
        name="name",
        cron_recurrence=CronRecurrenceExpression(
            monthdays=parse_monthdays_expr({"3", "5", "15"})
        ),
    )

    for month_day in [3, 5, 15]:
        assert (
            period.get_desired_state(
                MockLogger(), datetime(year=2023, month=4, day=month_day)
            )
            == "running"
        ), f"failed for {month_day}"


def test_monthday_only_is_stopped_on_other_monthdays() -> None:
    period = RunningPeriod(
        name="name",
        cron_recurrence=CronRecurrenceExpression(
            monthdays=parse_monthdays_expr({"3", "5", "15"})
        ),
    )
    _, days_in_month = calendar.monthrange(year=2023, month=4)
    for month_day in range(1, days_in_month + 1):
        if month_day in {3, 5, 15}:
            continue  # skip days it should be running
        assert (
            period.get_desired_state(
                MockLogger(), datetime(year=2023, month=4, day=month_day)
            )
            == "stopped"
        ), f"failed for {month_day}"
