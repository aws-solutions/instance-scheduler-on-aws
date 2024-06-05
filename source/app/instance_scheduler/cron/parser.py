# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Parse a string used in a period definition for a day-of-month, month-of-year, or
day-of-week field to an abstract representation.

Use knowledge of the features supported by Instance Scheduler periods. Though each field
supports different features, it is more convenient to allow any reasonable expression to
be parsed, then later use a validator for the specific field to raise errors. This way
we only have to define one set of parsers.
"""
import re
from collections.abc import Callable, Mapping
from dataclasses import replace
from functools import partial
from itertools import chain
from typing import Final

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
from instance_scheduler.cron.validator import (
    validate_monthdays_expression,
    validate_months_expression,
    validate_weekdays_expression,
)

PeriodDefnStr = set[str] | None


def parse_period_def(
    *,
    days_of_month: PeriodDefnStr,
    months_of_year: PeriodDefnStr,
    days_of_week: PeriodDefnStr,
) -> FullCronExpression:
    return FullCronExpression(
        days_of_month=parse_monthdays_expr(days_of_month),
        months_of_year=parse_months_expr(months_of_year),
        days_of_week=parse_weekdays_expr(days_of_week),
    )


def parse_months_expr(months_expr: PeriodDefnStr) -> CronExpression:
    result: Final = _parse_multi_general(months_expr, _month_name_to_value)
    validate_months_expression(result)
    return result


def parse_monthdays_expr(monthdays_expr: PeriodDefnStr) -> CronExpression:
    result: Final = _parse_multi_general(monthdays_expr, {})
    validate_monthdays_expression(result)
    return result


def parse_weekdays_expr(weekdays_expr: PeriodDefnStr) -> CronExpression:
    result: Final = _parse_multi_general(weekdays_expr, _weekday_name_to_value)
    validate_weekdays_expression(result)
    return result


def _parse_multi_general(
    exprs: PeriodDefnStr, domain: Mapping[str, int]
) -> CronExpression:
    if exprs is None:
        return CronAll()
    if len(exprs) == 0:
        raise ValueError("Zero-length string set is malformed")
    if len(exprs) == 1:
        return _parse_single_general(next(iter(exprs)), domain)
    else:
        return CronUnion(
            exprs=tuple(_parse_single_general(expr, domain) for expr in exprs)
        )


def _parse_single_general(expr: str, domain: Mapping[str, int]) -> CronExpression:
    exprs: Final = expr.split(",")
    if len(exprs) > 1:
        return CronUnion(
            exprs=tuple(_parse_single_general(sub_expr, domain) for sub_expr in exprs)
        )
    return _general_parse(exprs[0].strip().lower(), domain)


def _general_parse(expr: str, domain: Mapping[str, int]) -> CronExpression:
    parsers: Final[list[Callable[[str], CronExpression]]] = [
        partial(_parse_single_value_general, domain=domain),
        _parse_all_values,
        _parse_last_value,
        partial(_parse_step, domain=domain),
        partial(_parse_range, domain=domain),
        partial(_parse_nth_weekday, domain=domain),
        partial(_parse_last_weekday, domain=domain),
        _parse_nearest_weekday,
    ]
    for parser in parsers:
        try:
            return parser(expr)
        except ValueError:
            pass
    raise ValueError(f"Could not parse as any form of cron expression: {expr}")


# period definitions are not localized
month_names: Final = (
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
)
month_abbrs: Final = list(month_name[0:3] for month_name in month_names)
# month names can be the full month name, or the first three letters
_month_name_to_value: Final = {
    name: i + 1 for i, name in chain(enumerate(month_names), enumerate(month_abbrs))
}


# period definitions are not localized
weekday_names: Final = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)
weekday_abbrs: Final = list(weekday_name[0:3] for weekday_name in weekday_names)
# weekday names can be the full day name, or the first three letters
_weekday_name_to_value: Final = {
    name: i for i, name in chain(enumerate(weekday_names), enumerate(weekday_abbrs))
}


_single_value_re: Final = re.compile(r"^(\d+)$")


def _parse_single_numeric_value(expr: str) -> CronSingleValueNumeric:
    if not (match := _single_value_re.match(expr)):
        raise ValueError(f"Could not parse as single numeric value: {expr}")

    value: Final = int(match.group(1))
    return CronSingleValueNumeric(value=value)


def _parse_single_numeric_value_by_name(
    expr: str, domain: Mapping[str, int]
) -> CronSingleValueNumeric:
    if expr.lower() not in domain:
        raise ValueError(f"Could not parse as single name: {expr}")

    value: Final = domain[expr]
    return CronSingleValueNumeric(value=value)


def _parse_single_value_numeric(
    expr: str, domain: Mapping[str, int]
) -> CronSingleValueNumeric:
    parsers: Final[list[Callable[[str], CronSingleValueNumeric]]] = [
        _parse_single_numeric_value,
        partial(_parse_single_numeric_value_by_name, domain=domain),
    ]
    for parser in parsers:
        try:
            return parser(expr)
        except ValueError:
            pass
    raise ValueError(f"Could not parse as single value: {expr}")


def _parse_single_value_general(
    expr: str, domain: Mapping[str, int]
) -> CronSingleValueNumeric | CronSingleValueLast:
    parsers: Final[
        list[Callable[[str], CronSingleValueNumeric | CronSingleValueLast]]
    ] = [
        _parse_single_numeric_value,
        partial(_parse_single_numeric_value_by_name, domain=domain),
        _parse_last_value,
    ]
    for parser in parsers:
        try:
            return parser(expr)
        except ValueError:
            pass
    raise ValueError(f"Could not parse as single value: {expr}")


_last_re: Final = re.compile(r"^L$", flags=re.IGNORECASE)


def _parse_last_value(expr: str) -> CronSingleValueLast:
    if not _last_re.match(expr):
        raise ValueError(f"Could not parse as last value wildcard: {expr}")

    return CronSingleValueLast()


all_values_re: Final = re.compile(r"^[*?]$")


def _parse_all_values(expr: str) -> CronAll:
    if not all_values_re.match(expr):
        raise ValueError(f"Could not parse as all values wildcard: {expr}")

    return CronAll()


_step_re: Final = re.compile(r"^(.+)/.*(\d+).*$")


def _parse_step(expr: str, domain: Mapping[str, int]) -> CronRange:
    if not (match := _step_re.match(expr)):
        raise ValueError(f"Could not parse as step expression: {expr}")

    range_expr: Final = match.group(1)
    interval: Final = int(match.group(2).strip())

    try:
        range_ = _parse_range(range_expr, domain=domain)
        return replace(range_, interval=interval)
    except ValueError:
        pass

    try:
        start: Final = _parse_single_value_general(range_expr, domain)
        if isinstance(start, CronSingleValueLast):
            raise ValueError(f"Unable to parse step expression starting with L: {expr}")
        return CronRange(start=start, interval=interval)
    except ValueError:
        raise ValueError(f"Could not parse range of step expression: {expr}")


_range_re: Final = re.compile(r"^(.+)-(.+)$")


def _parse_range(expr: str, domain: Mapping[str, int]) -> CronRange:
    if not (match := _range_re.match(expr)):
        raise ValueError(f"Could not parse as range expression: {expr}")

    start: Final = _parse_single_value_general(match.group(1).strip(), domain)
    end: Final = _parse_single_value_general(match.group(2).strip(), domain)

    if isinstance(start, CronSingleValueLast):
        raise ValueError(f"Unable to parse range expression starting with L: {expr}")

    return CronRange(start=start, end=end)


_nth_weekday_re: Final = re.compile(r"^(.*)#(\d+)$")


def _parse_nth_weekday(expr: str, domain: Mapping[str, int]) -> CronExpression:
    if not (match := _nth_weekday_re.match(expr)):
        raise ValueError(f"Could not parse as Nth weekday expression: {expr}")

    return CronNthWeekday(
        day=_parse_single_value_numeric(match.group(1), domain), n=int(match.group(2))
    )


_last_weekday_re: Final = re.compile(r"^(.*)L$", flags=re.IGNORECASE)


def _parse_last_weekday(expr: str, domain: Mapping[str, int]) -> CronExpression:
    if not (match := _last_weekday_re.match(expr)):
        raise ValueError(f"Could not parse as last weekday expression: {expr}")

    return CronLastWeekday(day=_parse_single_value_numeric(match.group(1), domain))


_nearest_weekday_re: Final = re.compile(r"^(\d+)W$", flags=re.IGNORECASE)


def _parse_nearest_weekday(expr: str) -> CronExpression:
    if not (match := _nearest_weekday_re.match(expr)):
        raise ValueError(f"Could not parse as nearest weekday expression: {expr}")

    return CronNearestWeekday(value=CronSingleValueNumeric(int(match.group(1))))
