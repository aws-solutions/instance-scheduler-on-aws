# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from typing import Final

from pytest import raises

from instance_scheduler.cron.expression import (
    CronAll,
    CronLastWeekday,
    CronNthWeekday,
    CronRange,
    CronSingleValueLast,
    CronSingleValueNumeric,
    CronUnion,
)
from instance_scheduler.cron.parser import parse_weekdays_expr, weekday_names


def test_weekdays_parser_parses_none_as_all() -> None:
    assert parse_weekdays_expr(None) == CronAll()


def test_weekdays_parser_errors_on_empty_set() -> None:
    # string sets in DynamoDB are not allowed to be empty, so an empty set for a months
    # field would be malformed
    with raises(ValueError):
        parse_weekdays_expr(set())


def test_weekdays_parser_parses_wildcards() -> None:
    assert parse_weekdays_expr({"*"}) == CronAll()
    assert parse_weekdays_expr({"?"}) == CronAll()


def test_weekdays_parser_parses_single_numeric_values() -> None:
    for i in range(0, 7):
        assert parse_weekdays_expr({str(i)}) == CronSingleValueNumeric(value=i)


def test_weekdays_parser_parses_single_names() -> None:
    for i, day in enumerate(weekday_names):
        expected = CronSingleValueNumeric(value=i)
        # full name
        assert parse_weekdays_expr({day}) == expected
        # full name, all caps
        assert parse_weekdays_expr({day.upper()}) == expected
        # truncated
        assert parse_weekdays_expr({day[:3]}) == expected
        # truncated, all caps
        assert parse_weekdays_expr({day[:3].upper()}) == expected


def test_weekdays_parser_parses_numeric_ranges() -> None:
    assert parse_weekdays_expr({"0-2"}) == CronRange(
        start=CronSingleValueNumeric(value=0),
        end=CronSingleValueNumeric(value=2),
    )
    assert parse_weekdays_expr({"1-5"}) == CronRange(
        start=CronSingleValueNumeric(value=1),
        end=CronSingleValueNumeric(value=5),
    )
    assert parse_weekdays_expr({"5-6"}) == CronRange(
        start=CronSingleValueNumeric(value=5),
        end=CronSingleValueNumeric(value=6),
    )


def test_weekdays_parser_parses_numeric_ranges_wrapped() -> None:
    assert parse_weekdays_expr({"6-0"}) == CronRange(
        start=CronSingleValueNumeric(value=6),
        end=CronSingleValueNumeric(value=0),
    )
    assert parse_weekdays_expr({"2-1"}) == CronRange(
        start=CronSingleValueNumeric(value=2),
        end=CronSingleValueNumeric(value=1),
    )


def test_weekdays_parser_parses_comma_separated() -> None:
    assert parse_weekdays_expr({"1,3,6"}) == CronUnion(
        exprs=(
            CronSingleValueNumeric(value=1),
            CronSingleValueNumeric(value=3),
            CronSingleValueNumeric(value=6),
        )
    )
    assert parse_weekdays_expr({"4, 2, 5, 0, 6"}) == CronUnion(
        exprs=(
            CronSingleValueNumeric(value=4),
            CronSingleValueNumeric(value=2),
            CronSingleValueNumeric(value=5),
            CronSingleValueNumeric(value=0),
            CronSingleValueNumeric(value=6),
        )
    )


def test_weekdays_parser_parses_name_ranges() -> None:
    assert parse_weekdays_expr({"Monday-Friday"}) == CronRange(
        start=CronSingleValueNumeric(value=0),
        end=CronSingleValueNumeric(value=4),
    )
    assert parse_weekdays_expr({"Saturday-Sunday"}) == CronRange(
        start=CronSingleValueNumeric(value=5),
        end=CronSingleValueNumeric(value=6),
    )


def test_weekdays_parser_parses_name_ranges_wrapped() -> None:
    assert parse_weekdays_expr({"Sunday-Monday"}) == CronRange(
        start=CronSingleValueNumeric(value=6),
        end=CronSingleValueNumeric(value=0),
    )
    assert parse_weekdays_expr({"wednesday-tuesday"}) == CronRange(
        start=CronSingleValueNumeric(value=2),
        end=CronSingleValueNumeric(value=1),
    )


def test_weekdays_parser_parses_comma_separated_names() -> None:
    assert parse_weekdays_expr({"Tuesday,Thursday,Sunday"}) == CronUnion(
        exprs=(
            CronSingleValueNumeric(value=1),
            CronSingleValueNumeric(value=3),
            CronSingleValueNumeric(value=6),
        )
    )
    assert parse_weekdays_expr(
        {"Monday, Friday, Sunday, Tuesday, Wednesday"}
    ) == CronUnion(
        exprs=(
            CronSingleValueNumeric(value=0),
            CronSingleValueNumeric(value=4),
            CronSingleValueNumeric(value=6),
            CronSingleValueNumeric(value=1),
            CronSingleValueNumeric(value=2),
        )
    )


def test_weekdays_parser_parses_abbr_ranges() -> None:
    assert parse_weekdays_expr({"mon-fri"}) == CronRange(
        start=CronSingleValueNumeric(value=0),
        end=CronSingleValueNumeric(value=4),
    )
    assert parse_weekdays_expr({"Sat-Sun"}) == CronRange(
        start=CronSingleValueNumeric(value=5),
        end=CronSingleValueNumeric(value=6),
    )


def test_weekdays_parser_parses_abbr_ranges_wrapped() -> None:
    assert parse_weekdays_expr({"sun-mon"}) == CronRange(
        start=CronSingleValueNumeric(value=6),
        end=CronSingleValueNumeric(value=0),
    )
    assert parse_weekdays_expr({"Wed-Tue"}) == CronRange(
        start=CronSingleValueNumeric(value=2),
        end=CronSingleValueNumeric(value=1),
    )


def test_weekdays_parser_parses_comma_separated_abbrs() -> None:
    assert parse_weekdays_expr({"tue,thu,sun"}) == CronUnion(
        exprs=(
            CronSingleValueNumeric(value=1),
            CronSingleValueNumeric(value=3),
            CronSingleValueNumeric(value=6),
        )
    )
    assert parse_weekdays_expr({"Mon, Fri, Sun, Tue, Wed"}) == CronUnion(
        exprs=(
            CronSingleValueNumeric(value=0),
            CronSingleValueNumeric(value=4),
            CronSingleValueNumeric(value=6),
            CronSingleValueNumeric(value=1),
            CronSingleValueNumeric(value=2),
        )
    )


def test_weekdays_parser_parses_multiple_expressions() -> None:
    result: Final = parse_weekdays_expr({"2", "Sat-Sun", "Monday"})
    assert isinstance(result, CronUnion)
    assert set(result.exprs) == set(
        (
            CronSingleValueNumeric(value=2),
            CronRange(
                start=CronSingleValueNumeric(value=5),
                end=CronSingleValueNumeric(value=6),
            ),
            CronSingleValueNumeric(value=0),
        )
    )


def test_weekdays_parser_parses_last_day_wildcard() -> None:
    assert parse_weekdays_expr({"L"}) == CronSingleValueLast()


def test_weekdays_parser_parses_steps() -> None:
    assert parse_weekdays_expr({"Mon/2"}) == CronRange(
        start=CronSingleValueNumeric(value=0), interval=2
    )
    assert parse_weekdays_expr({"3/3"}) == CronRange(
        start=CronSingleValueNumeric(value=3), interval=3
    )
    assert parse_weekdays_expr({"Thursday/2"}) == CronRange(
        start=CronSingleValueNumeric(value=3), interval=2
    )


def test_weekdays_parser_parses_range_steps() -> None:
    assert parse_weekdays_expr({"1-5/3"}) == CronRange(
        start=CronSingleValueNumeric(value=1),
        end=CronSingleValueNumeric(value=5),
        interval=3,
    )
    assert parse_weekdays_expr({"Mon-Fri/2"}) == CronRange(
        start=CronSingleValueNumeric(value=0),
        end=CronSingleValueNumeric(value=4),
        interval=2,
    )
    assert parse_weekdays_expr({"Tuesday-Sunday/3"}) == CronRange(
        start=CronSingleValueNumeric(value=1),
        end=CronSingleValueNumeric(value=6),
        interval=3,
    )


def test_weekdays_parser_parses_nth_weekday() -> None:
    assert parse_weekdays_expr({"Thursday#3"}) == CronNthWeekday(
        day=CronSingleValueNumeric(value=3), n=3
    )
    assert parse_weekdays_expr({"mon#1"}) == CronNthWeekday(
        day=CronSingleValueNumeric(value=0), n=1
    )
    assert parse_weekdays_expr({"2#2"}) == CronNthWeekday(
        day=CronSingleValueNumeric(value=2), n=2
    )


def test_weekdays_parser_parses_last_weekday() -> None:
    assert parse_weekdays_expr({"1L"}) == CronLastWeekday(
        day=CronSingleValueNumeric(value=1)
    )
    assert parse_weekdays_expr({"ThursdayL"}) == CronLastWeekday(
        day=CronSingleValueNumeric(value=3)
    )
    assert parse_weekdays_expr({"monL"}) == CronLastWeekday(
        day=CronSingleValueNumeric(value=0)
    )


def test_invalid_value() -> None:
    with raises(ValueError):
        parse_weekdays_expr({"-1"})
    with raises(ValueError):
        parse_weekdays_expr({"7"})
    with raises(ValueError):
        parse_weekdays_expr({"wensday"})
    with raises(ValueError):
        parse_weekdays_expr({"fro"})
    with raises(ValueError):
        parse_weekdays_expr({"3-L"})
    with raises(ValueError):
        parse_weekdays_expr({"^-6"})


def test_invalid_nth_weekday() -> None:
    with raises(ValueError):
        parse_weekdays_expr({"0#6"})
    with raises(ValueError):
        parse_weekdays_expr({"0#-1"})
    with raises(ValueError):
        parse_weekdays_expr({"0#0"})
    with raises(ValueError):
        parse_weekdays_expr({"L-2"})  # range cannot start with L
