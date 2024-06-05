# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from typing import Final

from pytest import raises

from instance_scheduler.cron.expression import (
    CronAll,
    CronNearestWeekday,
    CronRange,
    CronSingleValueLast,
    CronSingleValueNumeric,
    CronUnion,
)
from instance_scheduler.cron.parser import parse_monthdays_expr


def test_monthdays_parser_parses_none_as_all_values() -> None:
    assert parse_monthdays_expr(None) == CronAll()


def test_monthdays_parser_errors_on_empty_set() -> None:
    # string sets in DynamoDB are not allowed to be empty, so an empty set for a
    # days-of-month field would be malformed
    with raises(ValueError):
        parse_monthdays_expr(set())


def test_monthdays_parser_parses_wildcards() -> None:
    assert parse_monthdays_expr({"*"}) == CronAll()
    assert parse_monthdays_expr({"?"}) == CronAll()


def test_monthdays_parser_parses_single_values() -> None:
    for i in range(1, 32):
        assert parse_monthdays_expr({str(i)}) == CronSingleValueNumeric(value=i)


def test_monthdays_parser_parses_ranges() -> None:
    assert parse_monthdays_expr({"5-20"}) == CronRange(
        start=CronSingleValueNumeric(value=5), end=CronSingleValueNumeric(value=20)
    )
    assert parse_monthdays_expr({"1-30"}) == CronRange(
        start=CronSingleValueNumeric(value=1), end=CronSingleValueNumeric(value=30)
    )


def test_monthdays_parser_parses_comma_separated() -> None:
    assert parse_monthdays_expr({"1,2,3,4,5"}) == CronUnion(
        exprs=(
            CronSingleValueNumeric(value=1),
            CronSingleValueNumeric(value=2),
            CronSingleValueNumeric(value=3),
            CronSingleValueNumeric(value=4),
            CronSingleValueNumeric(value=5),
        )
    )
    assert parse_monthdays_expr({"2, 8, 10, 20, 22"}) == CronUnion(
        exprs=(
            CronSingleValueNumeric(value=2),
            CronSingleValueNumeric(value=8),
            CronSingleValueNumeric(value=10),
            CronSingleValueNumeric(value=20),
            CronSingleValueNumeric(value=22),
        )
    )


def test_monthdays_parser_parses_last_day_wildcard() -> None:
    assert parse_monthdays_expr({"L"}) == CronSingleValueLast()
    assert parse_monthdays_expr({"6-L"}) == CronRange(
        start=CronSingleValueNumeric(value=6), end=CronSingleValueLast()
    )
    assert parse_monthdays_expr({"3-L/2"}) == CronRange(
        start=CronSingleValueNumeric(value=3), end=CronSingleValueLast(), interval=2
    )


def test_monthdays_parser_parses_steps() -> None:
    assert parse_monthdays_expr({"1/7"}) == CronRange(
        start=CronSingleValueNumeric(value=1), interval=7
    )


def test_monthdays_parser_parses_range_steps() -> None:
    assert parse_monthdays_expr({"15-30/3"}) == CronRange(
        start=CronSingleValueNumeric(value=15),
        end=CronSingleValueNumeric(value=30),
        interval=3,
    )


def test_monthdays_parser_parses_nearest_weekday_wildcard() -> None:
    assert parse_monthdays_expr({"17W"}) == CronNearestWeekday(
        value=CronSingleValueNumeric(value=17)
    )


def test_monthdays_parser_parses_multiple_expressions() -> None:
    result: Final = parse_monthdays_expr({"2", "13-15", "5-8"})
    assert isinstance(result, CronUnion)
    assert set(result.exprs) == set(
        (
            CronSingleValueNumeric(value=2),
            CronRange(
                start=CronSingleValueNumeric(value=13),
                end=CronSingleValueNumeric(value=15),
            ),
            CronRange(
                start=CronSingleValueNumeric(value=5),
                end=CronSingleValueNumeric(value=8),
            ),
        )
    )


def test_monthdays_parser_errors_on_invalid_values() -> None:
    with raises(ValueError):
        parse_monthdays_expr({"W"})
    with raises(ValueError):
        parse_monthdays_expr({"32W"})
    with raises(ValueError):
        parse_monthdays_expr({"36"})
    with raises(ValueError):
        parse_monthdays_expr({"2W-15"})
    with raises(ValueError):
        parse_monthdays_expr({"L-13"})  # range cannot start with L
