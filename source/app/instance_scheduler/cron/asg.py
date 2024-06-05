# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Convert cron expressions into recurrence strings for AutoScaling Group Scheduled
Scaling Actions"""
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
)
from instance_scheduler.cron.parser import month_abbrs, weekday_abbrs

# month names are one-indexed
_month_value_to_abbr: Final = {i + 1: name for i, name in enumerate(month_abbrs)}


def to_asg_expr_months(expr: CronExpression) -> str:
    match expr:
        case CronAll():
            return "*"
        case CronSingleValueNumeric(value=_):
            return _month_value_to_abbr[expr.value]
        case CronRange(start=_, end=None, interval=_):
            return f"{to_asg_expr_months(expr.start)}/{expr.interval}"
        case CronRange(start=_, end=_, interval=1):
            if not expr.end:
                raise ValueError()
            return f"{to_asg_expr_months(expr.start)}-{to_asg_expr_months(expr.end)}"
        case CronRange(start=_, end=_, interval=_):
            if not expr.end:
                raise ValueError()
            return f"{to_asg_expr_months(expr.start)}-{to_asg_expr_months(expr.end)}/{expr.interval}"
        case CronUnion():
            return ",".join(to_asg_expr_months(sub_expr) for sub_expr in expr.exprs)
        case CronSingleValueLast():
            return to_asg_expr_months(CronSingleValueNumeric(value=12))
        case CronNearestWeekday():
            raise ValueError("Nearest weekday in month-of-year expression is malformed")
        case CronNthWeekday():
            raise ValueError("Nth weekday in month-of-year expression is malformed")
        case CronLastWeekday():
            raise ValueError("Last weekday in month-of-year expression is malformed")


def to_asg_expr_monthdays(expr: CronExpression) -> str:
    match expr:
        case CronAll():
            return "*"
        case CronSingleValueNumeric(value=_):
            return str(expr.value)
        case CronSingleValueLast():
            return "L"
        case CronRange(start=_, end=_, interval=1):
            if expr.end is None:
                raise ValueError(
                    "Range with only start and interval of one is malformed"
                )
            return (
                f"{to_asg_expr_monthdays(expr.start)}-{to_asg_expr_monthdays(expr.end)}"
            )
        case CronRange(start=_, end=None, interval=_):
            return f"{to_asg_expr_monthdays(expr.start)}/{expr.interval}"
        case CronRange(start=_, end=_, interval=_):
            if expr.end is None:
                # mypy is unable to narrow this type appropriately
                raise RuntimeError("Unexpected pattern matching behavior")
            return f"{to_asg_expr_monthdays(expr.start)}-{to_asg_expr_monthdays(expr.end)}/{expr.interval}"
        case CronUnion():
            return ",".join(to_asg_expr_monthdays(sub_expr) for sub_expr in expr.exprs)
        case CronNearestWeekday():
            raise NotImplementedError(
                "Nearest weekday not supported by underlying service"
            )
        case CronNthWeekday():
            raise ValueError("Nth weekday in day-of-month expression is malformed")
        case CronLastWeekday():
            raise ValueError("Last weekday in day-of-month expression is malformed")


# Instance Scheduler uses zero to mean Monday, unlike most cron implementations
_weekday_value_to_abbr: Final = {i: name for i, name in enumerate(weekday_abbrs)}


def to_asg_expr_weekdays(expr: CronExpression) -> str:
    match expr:
        case CronAll():
            return "*"
        case CronSingleValueNumeric(value=_):
            return _weekday_value_to_abbr[expr.value]
        case CronSingleValueLast():
            return "L"
        case CronRange(start=_, end=_, interval=1):
            if expr.end is None:
                raise ValueError(
                    "Range with only start and interval of one is malformed"
                )
            return (
                f"{to_asg_expr_weekdays(expr.start)}-{to_asg_expr_weekdays(expr.end)}"
            )
        case CronRange(start=_, end=None, interval=_):
            return f"{to_asg_expr_weekdays(expr.start)}/{expr.interval}"
        case CronRange(start=_, end=_, interval=_):
            if expr.end is None:
                # mypy is unable to narrow this type appropriately
                raise RuntimeError("Unexpected pattern matching behavior")
            return f"{to_asg_expr_weekdays(expr.start)}-{to_asg_expr_weekdays(expr.end)}/{expr.interval}"
        case CronUnion():
            return ",".join(to_asg_expr_weekdays(sub_expr) for sub_expr in expr.exprs)
        case CronNearestWeekday():
            raise ValueError("Nearest weekday in day-of-week expression is malformed")
        case CronNthWeekday():
            raise NotImplementedError("Nth weekday not supported by underlying service")
        case CronLastWeekday():
            raise NotImplementedError(
                "Last weekday not supported by underlying service"
            )
