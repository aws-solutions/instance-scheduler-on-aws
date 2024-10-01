# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from datetime import datetime, timezone

import pytest

from instance_scheduler.cron.cron_recurrence_expression import CronRecurrenceExpression
from instance_scheduler.cron.cron_to_running_period import (
    IntDomain,
    _range_to_discrete_values,
    _resolve_first_occurrence_of_weekday_in_month,
    months_cron_expr_contains,
    resolve_nth_weekday_as_monthday,
)
from instance_scheduler.cron.expression import CronRange
from instance_scheduler.cron.parser import _parse_multi_general, parse_months_expr


def test_in_period_check_months() -> None:
    assert months_cron_expr_contains(
        parse_months_expr({"*"}),
        datetime(year=2024, month=1, day=15, tzinfo=timezone.utc),
    )

    assert months_cron_expr_contains(
        parse_months_expr({"jan"}),
        datetime(year=2024, month=1, day=15, tzinfo=timezone.utc),
    )
    assert not months_cron_expr_contains(
        parse_months_expr({"sep"}),
        datetime(year=2024, month=2, day=15, tzinfo=timezone.utc),
    )
    assert months_cron_expr_contains(
        parse_months_expr({"3"}),
        datetime(year=2024, month=3, day=15, tzinfo=timezone.utc),
    )
    assert not months_cron_expr_contains(
        parse_months_expr({"8"}),
        datetime(year=2024, month=9, day=15, tzinfo=timezone.utc),
    )


@pytest.mark.parametrize(
    "expr,expected_result",
    [
        ("1-4", {1, 2, 3, 4}),  # simple no-step case
        ("1-7/2", {1, 3, 5, 7}),  # simple step case
        ("1-7/4", {1, 5}),  # larger step with truncation
        ("1-L/2", {1, 3, 5, 7}),  # simple step case with L
        ("5-4/2", {5, 7, 2, 4}),  # wrap
        ("6-4/2", {6, 1, 3}),  # wrap
        ("0/2", {2, 4, 6}),  # start before domain (iterates through domain)
        ("3-12/2", {3, 5, 7}),  # truncate overruns to within domain
        ("4-4/2", {4}),  # -4/2 adds nothing, but should also not be an invalid format
        ("8-L/2", set()),  # start after domain (no valid days)
        ("8/2", set()),  # start after domain (no valid days)
        ("8-12/2", set()),  # start after domain (no valid days)
    ],
)
def test_range_wraps_as_expected(expr: str, expected_result: set[int]) -> None:
    # using 1-7 (weekdays) to make scenarios easier/more obvious
    domain = domain = IntDomain(start=1, end=7)
    parsed_range = _parse_multi_general({expr}, {})
    assert isinstance(parsed_range, CronRange)

    assert _range_to_discrete_values(parsed_range, domain) == expected_result


@pytest.mark.parametrize(
    "expr, expected_day_to_run_on",
    [
        ("1W", 3),  # Saturday as 1st of month, go forward to Monday
        ("2W", 3),  # Sunday, run on the Monday after
        ("3W", 3),  # Monday, no need to adjust
        ("15W", 14),  # Saturday, run on the Friday before
        ("16W", 17),  # Sunday, run on the Monday after
        ("29W", 28),  # Saturday, run on the Friday before
        ("30W", 28),  # Sunday as last of month, go backward to Friday
    ],
)
def test_nearest_weekday_runs_as_expected(
    expr: str, expected_day_to_run_on: int
) -> None:
    # april 2023 is a month that started on a Saturday and ended on a Sunday.
    parsed_expr = CronRecurrenceExpression.parse(monthdays={expr})
    for day in range(1, 31):
        expected_result = day == expected_day_to_run_on
        actual_result = parsed_expr.contains(datetime(year=2023, month=4, day=day))
        assert (
            expected_result == actual_result
        ), f"Expected {expected_result}, got {actual_result}, on day {day}"


@pytest.mark.parametrize(
    "expr, expected_day_to_run_on",
    [
        ("monL", 29),
        ("1L", 30),
        ("WedL", 24),
        ("3L", 25),
        ("FRIL", 26),
        ("satL", 27),
        ("6L", 28),
    ],
)
def test_last_weekday_runs_on_expected_day(
    expr: str, expected_day_to_run_on: int
) -> None:
    # The last day of April 2024 is a tuesday
    parsed_expr = CronRecurrenceExpression.parse(weekdays={expr})
    for day in range(1, 31):
        expected_result = day == expected_day_to_run_on
        actual_result = parsed_expr.contains(datetime(year=2024, month=4, day=day))
        assert (
            expected_result == actual_result
        ), f"Expected {expected_result}, got {actual_result}, on day {day}"


@pytest.mark.parametrize(
    "expr, expected_day_to_run_on",
    [
        ("mon#1", 1),
        ("tue#1", 2),
        ("wed#1", 3),
        ("thu#1", 4),
        ("fri#1", 5),
        ("sat#1", 6),
        ("sun#1", 7),
        ("mon#2", 8),
        ("mon#3", 15),
        ("mon#4", 22),
        ("mon#5", 29),
        ("TUE#3", 16),
        ("sun#2", 14),
        ("Tue#5", 30),  # last day of month
    ],
)
def test_nth_weekday_runs_on_expected_day(
    expr: str, expected_day_to_run_on: int
) -> None:
    # using April 2024 as test month.
    parsed_expr = CronRecurrenceExpression.parse(weekdays={expr})
    for day in range(1, 31):
        expected_result = day == expected_day_to_run_on
        actual_result = parsed_expr.contains(datetime(year=2024, month=4, day=day))
        assert (
            expected_result == actual_result
        ), f"Expected {expected_result}, got {actual_result}, on day {day}"


@pytest.mark.parametrize(
    "expr",
    [
        # ("mon#6"), illegal format
        "Thu#5"
    ],
)
def test_nth_weekday_does_not_run_when_weekday_does_not_exist_in_month(
    expr: str,
) -> None:
    # using April 2024 as test month.
    parsed_expr = CronRecurrenceExpression.parse(weekdays={expr})
    for day in range(1, 31):
        result = parsed_expr.contains(datetime(year=2024, month=4, day=day))
        assert result is not True, f"Expected never to run, but ran on day {day}"


@pytest.mark.parametrize(
    "weekday, expected",
    [
        # ("mon#6"), illegal format
        (0, 1),
        (1, 2),
        (2, 3),
        (3, 4),
        (4, 5),
        (5, 6),
        (6, 7),
    ],
)
def test_resolve_first_occurrence_of_weekday_in_month_returns_expected(
    weekday: int, expected: int
) -> None:
    # using April 2024 as test month.
    reference_date = datetime(year=2024, month=4, day=6)
    assert _resolve_first_occurrence_of_weekday_in_month(
        weekday, reference_date
    ) == reference_date.replace(day=expected)


# using september 2024 which starts on a Sunday
# su mo tu we th fr sa
# 01 02 03 04 05 06 07
# 08 09 10 11 12 13 14
# 15 16 17 18 19 20 21
# 22 23 24 25 26 27 28
# 29 30 01
@pytest.mark.parametrize(
    "weekday, n, expected",
    [
        (0, 1, 2),  # first monday
        (6, 1, 1),  # first sunday
        (6, 2, 8),  # second sunday
        (4, 3, 20),  # 3rd friday
        (5, 3, 21),  # 3rd saturday
        (5, 4, 28),  # 4th saturday
        (1, 1, 3),  # 1st tuesday
        (1, 3, 17),  # 3rd tuesday
    ],
)
def test_resolve_nth_weekday_as_monthday_returns_expected(
    weekday: int, n: int, expected: int
) -> None:
    reference_date = datetime(year=2024, month=9, day=1)
    assert resolve_nth_weekday_as_monthday(weekday, n, reference_date) == expected
