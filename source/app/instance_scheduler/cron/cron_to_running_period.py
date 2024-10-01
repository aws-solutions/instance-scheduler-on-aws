# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Determine if a `datetime` satisfies a recurrence expression"""
from calendar import monthrange
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from instance_scheduler.cron.expression import (
    CronAll,
    CronExpression,
    CronLastWeekday,
    CronNearestWeekday,
    CronNthWeekday,
    CronRange,
    CronSingleValueLast,
    CronSingleValueNumeric,
    CronUnion,
    FullCronExpression,
)

"""
range/wrapping behavior notes (last updated 3/1/24)

    Correct handling of wrapping behavior presents some somewhat unintuitive problems when the domain changes over time
like it does for monthdays. For example. suppose the expr "30-L" is used as a monthday expression. in various months/years
this can resolve to 30-30, 30-31, (both simple cases) and 30-28 (a potential wrap case). It is assumed in this last case
that 30-L in a month with 28 days should take no action at all

    However another possible scenario is an expression of 21-9/2 which might reasonably be interpreted as 
"starting on the 21st, run every 2nd day until the 9th of the next month, but don't run on the 10th-20th". 
In specific terms: In a month with 30 days, run on {21, 23, 25, 27, 29} in the current month and {1, 3, 5, 7, 9} 
in the next month. However, this is NOT the normal behavior of cron because cron is typically evaluated within the context of 
the current month only (meaning that wrapping accounts for the number of days in the current month, not the prev month).
For example, in the transition between March and April, this cron would resolve to {2, 4, 6, 8, 21, 23, 25, 27, 31} 
in March (with 31 days) followed by {1, 3, 5, 7, 9, 21, 23, 25, 27, 29} in April (with 30 days) leading to two 
concurrent days being scheduled (Mar 31st and Apr 1st).

    We do not currently attempt to address this peculiarity and instead simply make the assertion that while days/months
(with consistent domains of 0-6 and 1-12 respectively) do support wrapping, monthdays do NOT wrap. In addition
If an expr specifies a start that is after the end of a given domain, the expression will resolve to an empty set of
running values and WILL NOT WRAP. Thus a weekday expression of "7-3" would never be true because weekdays only go from
0-6 and we will not auto-wrap this malformed expression; likewise a monthday expression of 30-L will run on the 30th/31st 
of every month when possible and will NOT run at all in months with < 30 days.

    Similarly ranges that start from L and plan to wrap around (such as L-5) are not considered a legal format 
(this being enforced by the typing of CronRange). This leaves open the option to potentially support "L-5" as 
"the last 5 days/months of the week/month/year" in the future.
"""  # noqa: W291


def in_period(expr: FullCronExpression, dt: datetime) -> bool:
    """Does `dt` satisfy the recurrence defined in `expr`"""
    # When both days-of-month and days-of-week are specified, the normal behavior for
    # cron is to trigger on a day that satisfies either expression. However, Instance
    # Scheduler has historically checked that a date satisfies all fields. If a field is
    # missing from the period definition, it is considered satisfied. This means that if
    # a running period is not missing (`None`) and not a wildcard for all values, only
    # days that satisfy the intersection of days-of-month and days-of-week satisfy the
    # expression. This is a departure from standard cron behavior that may surprise
    # customers.
    return all(
        (
            monthday_cron_expr_contains(expr.days_of_month, dt),
            months_cron_expr_contains(expr.months_of_year, dt),
            weekday_cron_expr_contains(expr.days_of_week, dt),
        )
    )


def months_cron_expr_contains(expr: CronExpression, dt: datetime) -> bool:
    """
    Does `dt` satisfy `expr` when interpreted as a months-of-year expression
    note: dt is assumed to be timezone-aware and already translated into the correct timezone
    """
    months_domain = IntDomain(1, 12)

    match expr:
        case CronAll():
            return True
        case CronSingleValueNumeric():
            return dt.month == expr.value
        case CronRange():
            running_months = _range_to_discrete_values(expr, months_domain)
            return dt.month in running_months
        case CronUnion():
            return any(
                months_cron_expr_contains(sub_expr, dt) for sub_expr in expr.exprs
            )
        case CronSingleValueLast():
            return dt.month == months_domain.end
        case CronNearestWeekday():
            raise ValueError("Nearest Weekday not supported by month expression")
        case CronNthWeekday():
            raise ValueError("Nth Weekday not supported by month expression")
        case CronLastWeekday():
            raise ValueError("Last Weekday not supported by month expression")


def monthday_cron_expr_contains(expr: CronExpression, dt: datetime) -> bool:
    """Does `dt` satisfy `expr` when interpreted as a days-of-month expression"""
    _, days_in_month = monthrange(dt.year, dt.month)
    monthdays_domain = IntDomain(1, days_in_month)

    match expr:
        case CronAll():
            return True
        case CronSingleValueNumeric():
            return dt.day == expr.value
        case CronRange():
            return dt.day in _range_to_discrete_values(expr, monthdays_domain)
        case CronUnion():
            return any(
                monthday_cron_expr_contains(sub_expr, dt) for sub_expr in expr.exprs
            )
        case CronSingleValueLast():
            return dt.day == monthdays_domain.end
        case CronNearestWeekday():
            nearest_weekday = resolve_nearest_weekday_as_monthday(expr.value.value, dt)
            return dt.day == nearest_weekday
        case CronNthWeekday():
            raise ValueError("Nth Weekday not supported by monthday expression")
        case CronLastWeekday():
            raise ValueError("Last Weekday not supported by monthday expression")


def weekday_cron_expr_contains(expr: CronExpression, dt: datetime) -> bool:
    """Does `dt` satisfy `expr` when interpreted as a days-of-week expression"""
    weekdays_domain = IntDomain(0, 6)

    match expr:
        case CronAll():
            return True
        case CronSingleValueNumeric():
            return dt.weekday() == expr.value
        case CronRange():
            return dt.weekday() in _range_to_discrete_values(expr, weekdays_domain)
        case CronUnion():
            return any(
                weekday_cron_expr_contains(sub_expr, dt) for sub_expr in expr.exprs
            )
        case CronSingleValueLast():
            return dt.weekday() == weekdays_domain.end
        case CronNearestWeekday():
            raise NotImplementedError
        case CronNthWeekday():
            return (
                resolve_nth_weekday_as_monthday(
                    weekday=expr.day.value, n=expr.n, reference_date=dt
                )
                == dt.day
            )
        case CronLastWeekday():
            return resolve_last_weekday_as_monthday(expr.day.value, dt) == dt.day


def resolve_nearest_weekday_as_monthday(monthday: int, reference_date: date) -> int:
    """resolve the nearest weekday to the monthday in the month of the reference date"""
    target_date = date(
        year=reference_date.year, month=reference_date.month, day=monthday
    )
    match target_date.weekday():
        case 5:  # saturday
            if monthday == 1:
                # going backward would be the prev month, so go forward instead
                return monthday + 2
            else:
                return monthday - 1
        case 6:  # sunday
            _, last_day_of_month = monthrange(target_date.year, target_date.month)
            if monthday == last_day_of_month:
                # going forward would be the next month, so go backward instead
                return monthday - 2
            else:
                return monthday + 1
        case _:
            return monthday


def resolve_last_weekday_as_monthday(weekday: int, reference_date: date) -> int:
    """resolve the last weekday within the month of the reference date"""
    _, last_day_of_month = monthrange(reference_date.year, reference_date.month)

    # iterate backwards from the last day until we find the desired weekday
    for monthday in reversed(range(1, last_day_of_month + 1)):
        pointer_date = date(
            year=reference_date.year, month=reference_date.month, day=monthday
        )
        if pointer_date.weekday() == weekday:
            return monthday

    # catch all that should not be possible assuming weekday is between 0-6
    raise ValueError(f"weekday {weekday} not found within month of {reference_date}")


def resolve_nth_weekday_as_monthday(weekday: int, n: int, reference_date: date) -> int:
    """
    resolves the monthday of the nth occurrence of the specified weekday or -1 if there is no such nth occurrence
    """
    first_occurrence = _resolve_first_occurrence_of_weekday_in_month(
        weekday, reference_date
    )
    nth_occurrence = first_occurrence + timedelta(days=7 * (n - 1))
    if nth_occurrence.month == reference_date.month:
        return nth_occurrence.day
    else:
        return -1


def _resolve_first_occurrence_of_weekday_in_month(
    weekday: int, reference_date: date
) -> date:
    reference_date = reference_date.replace(day=1)

    offset_to_first_day = weekday - reference_date.weekday() % 7
    if offset_to_first_day < 0:
        offset_to_first_day += 7
    return reference_date + timedelta(days=offset_to_first_day)


@dataclass
class IntDomain:
    start: int
    end: int

    def __post_init__(self) -> None:
        assert self.start <= self.end, "start must be less than end"

    def width(self) -> int:
        return self.end - self.start

    def contains(self, val: int) -> bool:
        return self.start <= val <= self.end


def _range_to_discrete_values(expr: CronRange, domain: IntDomain) -> set[int]:

    start = _cron_single_val_to_int(expr.start, domain)
    end = _cron_single_val_to_int(expr.end, domain)

    if start > domain.end:
        return set()

    will_wrap = start > end
    pointer = start
    values = set()
    while will_wrap or pointer <= end:
        if domain.contains(pointer):
            values.add(pointer)

        pointer += expr.interval
        if will_wrap and pointer > domain.end:
            pointer -= domain.width() + 1
            will_wrap = False

    return values


def _cron_single_val_to_int(
    expr: CronSingleValueNumeric | CronSingleValueLast | None, domain: IntDomain
) -> int:
    match expr:
        case CronSingleValueNumeric():
            return expr.value
        case CronSingleValueLast() | None:
            return domain.end
