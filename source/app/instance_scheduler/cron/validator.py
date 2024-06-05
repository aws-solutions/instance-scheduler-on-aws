# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Validate a parsed cron expression in the context of the Instance Scheduler
implementation and the specific field. There are potentially valid strings that we have
rejected in the past, such as the last wildcard "L" in a range expresssion within a
month-of-year expression.
"""
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


def validate_months_expression(expr: CronExpression) -> None:
    match expr:
        case CronAll():
            return
        case CronSingleValueNumeric():
            if expr.value < 1 or expr.value > 12:
                raise ValueError(
                    f"Numeric value in month-of-year expression must be between 1 and 12: {expr.value}"
                )
        case CronSingleValueLast():
            # backwards compatibility reasons only. we could likely allow this without issue now
            raise ValueError("Last value wildcard not supported in months expressions")
        case CronRange():
            if isinstance(expr.start, CronSingleValueLast) or isinstance(
                expr.end, CronSingleValueLast
            ):
                raise ValueError(
                    "Last value wildcard in month-of-year range expression is malformed"
                )
            validate_months_expression(expr.start)
            if expr.end is not None:
                validate_months_expression(expr.end)
        case CronUnion():
            for sub_expr in expr.exprs:
                validate_months_expression(sub_expr)
        case CronNearestWeekday():
            raise ValueError("Nearest weekday in month-of-year expression is malformed")
        case CronNthWeekday():
            raise ValueError("Nth weekday in month-of-year expression is malformed")
        case CronLastWeekday():
            raise ValueError("Last weekday in month-of-year expression is malformed")


def validate_monthdays_expression(expr: CronExpression) -> None:
    match expr:
        case CronAll():
            return
        case CronSingleValueNumeric():
            if expr.value < 1 or expr.value > 31:
                raise ValueError(
                    f"Numeric value in day-of-month expression must be between 1 and 31: {expr.value}"
                )
        case CronSingleValueLast():
            return
        case CronRange():
            validate_monthdays_expression(expr.start)
            if expr.end is not None:
                validate_monthdays_expression(expr.end)
            if (
                isinstance(expr.end, CronSingleValueNumeric)
                and expr.start.value > expr.end.value
            ):
                raise ValueError(
                    f"Range wrapping is not supported for monthday expressions. received: {expr.start.value}-{expr.end.value}"
                )

        case CronUnion():
            for sub_expr in expr.exprs:
                validate_monthdays_expression(sub_expr)
        case CronNearestWeekday():
            validate_monthdays_expression(expr.value)
        case CronNthWeekday():
            raise ValueError("Nth weekday in day-of-month expression is malformed")
        case CronLastWeekday():
            raise ValueError("Last weekday in day-of-month expression is malformed")


def validate_weekdays_expression(expr: CronExpression) -> None:
    match expr:
        case CronAll():
            return
        case CronSingleValueNumeric():
            if expr.value < 0 or expr.value > 6:
                raise ValueError(
                    f"Numeric value in day-of-week expression must be between 0 and 6: {expr.value}"
                )
        case CronSingleValueLast():
            return
        case CronRange():
            if isinstance(expr.start, CronSingleValueLast) or isinstance(
                expr.end, CronSingleValueLast
            ):
                raise ValueError(
                    "Last value wildcard in day-of-week range expression is malformed"
                )
            validate_weekdays_expression(expr.start)
            if expr.end is not None:
                validate_weekdays_expression(expr.end)
        case CronUnion():
            for sub_expr in expr.exprs:
                validate_weekdays_expression(sub_expr)
        case CronNearestWeekday():
            raise ValueError("Nearest weekday in day-of-week expression is malformed")
        case CronNthWeekday():
            if expr.n < 1 or expr.n > 5:
                raise ValueError(
                    f"Value for N in Nth weekday expression in day-of-week expression must be between 1 and 5: {expr.n}"
                )
            validate_weekdays_expression(expr.day)
        case CronLastWeekday():
            validate_weekdays_expression(expr.day)
