# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from pytest import raises

from instance_scheduler.cron.expression import (
    CronAll,
    CronRange,
    CronSingleValueNumeric,
    CronUnion,
)
from instance_scheduler.cron.parser import month_names, parse_months_expr


def test_months_parser_parses_none_as_all() -> None:
    assert parse_months_expr(None) == CronAll()


def test_months_parser_errors_on_empty_set() -> None:
    # string sets in DynamoDB are not allowed to be empty, so an empty set for a months
    # field would be malformed
    with raises(ValueError):
        parse_months_expr(set())


def test_months_parser_parses_wildcards() -> None:
    assert parse_months_expr({"*"}) == CronAll()
    assert parse_months_expr({"?"}) == CronAll()


def test_months_parser_parses_single_numeric_values() -> None:
    for i in range(1, 13):
        assert parse_months_expr({str(i)}) == CronSingleValueNumeric(value=i)


def test_months_parser_parses_single_names() -> None:
    for i, month in enumerate(month_names):
        expected = CronSingleValueNumeric(value=i + 1)
        # full name
        assert parse_months_expr({month}) == expected
        # full name, all caps
        assert parse_months_expr({month.upper()}) == expected
        # truncated
        assert parse_months_expr({month[:3]}) == expected
        # truncated, all caps
        assert parse_months_expr({month[:3].upper()}) == expected


def test_months_parser_parses_numeric_ranges() -> None:
    assert parse_months_expr({"1-3"}) == CronRange(
        start=CronSingleValueNumeric(value=1),
        end=CronSingleValueNumeric(value=3),
    )
    assert parse_months_expr({"7-8"}) == CronRange(
        start=CronSingleValueNumeric(value=7),
        end=CronSingleValueNumeric(value=8),
    )
    assert parse_months_expr({"1-12"}) == CronRange(
        start=CronSingleValueNumeric(value=1),
        end=CronSingleValueNumeric(value=12),
    )


def test_months_parser_parses_numeric_ranges_wrapped() -> None:
    assert parse_months_expr({"12-1"}) == CronRange(
        start=CronSingleValueNumeric(value=12),
        end=CronSingleValueNumeric(value=1),
    )
    assert parse_months_expr({"2-1"}) == CronRange(
        start=CronSingleValueNumeric(value=2),
        end=CronSingleValueNumeric(value=1),
    )


def test_months_parser_parses_comma_separated() -> None:
    assert parse_months_expr({"1,3,7"}) == CronUnion(
        exprs=(
            CronSingleValueNumeric(value=1),
            CronSingleValueNumeric(value=3),
            CronSingleValueNumeric(value=7),
        )
    )
    assert parse_months_expr({"10, 2, 12, 11, 6"}) == CronUnion(
        exprs=(
            CronSingleValueNumeric(value=10),
            CronSingleValueNumeric(value=2),
            CronSingleValueNumeric(value=12),
            CronSingleValueNumeric(value=11),
            CronSingleValueNumeric(value=6),
        )
    )


def test_months_parser_parses_name_ranges() -> None:
    assert parse_months_expr({"January-June"}) == CronRange(
        start=CronSingleValueNumeric(value=1),
        end=CronSingleValueNumeric(value=6),
    )
    assert parse_months_expr({"July-November"}) == CronRange(
        start=CronSingleValueNumeric(value=7),
        end=CronSingleValueNumeric(value=11),
    )


def test_months_parser_parses_name_ranges_wrapped() -> None:
    assert parse_months_expr({"October-June"}) == CronRange(
        start=CronSingleValueNumeric(value=10),
        end=CronSingleValueNumeric(value=6),
    )
    assert parse_months_expr({"July-June"}) == CronRange(
        start=CronSingleValueNumeric(value=7),
        end=CronSingleValueNumeric(value=6),
    )


def test_months_parser_parses_comma_separated_names() -> None:
    assert parse_months_expr({"january,march,july"}) == CronUnion(
        exprs=(
            CronSingleValueNumeric(value=1),
            CronSingleValueNumeric(value=3),
            CronSingleValueNumeric(value=7),
        )
    )
    assert parse_months_expr(
        {"october, february, december, november, june"}
    ) == CronUnion(
        exprs=(
            CronSingleValueNumeric(value=10),
            CronSingleValueNumeric(value=2),
            CronSingleValueNumeric(value=12),
            CronSingleValueNumeric(value=11),
            CronSingleValueNumeric(value=6),
        )
    )


def test_months_parser_parses_abbr_ranges() -> None:
    assert parse_months_expr({"jan-jun"}) == CronRange(
        start=CronSingleValueNumeric(value=1),
        end=CronSingleValueNumeric(value=6),
    )
    assert parse_months_expr({"jul-nov"}) == CronRange(
        start=CronSingleValueNumeric(value=7),
        end=CronSingleValueNumeric(value=11),
    )


def test_months_parser_parses_abbr_ranges_wrapped() -> None:
    assert parse_months_expr({"Oct-Jun"}) == CronRange(
        start=CronSingleValueNumeric(value=10),
        end=CronSingleValueNumeric(value=6),
    )
    assert parse_months_expr({"jul-jun"}) == CronRange(
        start=CronSingleValueNumeric(value=7),
        end=CronSingleValueNumeric(value=6),
    )


def test_months_parser_parses_comma_separated_abbrs() -> None:
    assert parse_months_expr({"jan,mar,jul"}) == CronUnion(
        exprs=(
            CronSingleValueNumeric(value=1),
            CronSingleValueNumeric(value=3),
            CronSingleValueNumeric(value=7),
        )
    )
    assert parse_months_expr({"Oct, Feb, Dec, Nov, Jun"}) == CronUnion(
        exprs=(
            CronSingleValueNumeric(value=10),
            CronSingleValueNumeric(value=2),
            CronSingleValueNumeric(value=12),
            CronSingleValueNumeric(value=11),
            CronSingleValueNumeric(value=6),
        )
    )


def test_months_parser_parses_steps() -> None:
    assert parse_months_expr({"4/2"}) == CronRange(
        start=CronSingleValueNumeric(value=4), interval=2
    )
    assert parse_months_expr({"Jan/3"}) == CronRange(
        start=CronSingleValueNumeric(value=1), interval=3
    )


def test_months_parser_parses_range_steps() -> None:
    assert parse_months_expr({"3-9/2"}) == CronRange(
        start=CronSingleValueNumeric(value=3),
        end=CronSingleValueNumeric(value=9),
        interval=2,
    )
    assert parse_months_expr({"feb-sep/6"}) == CronRange(
        start=CronSingleValueNumeric(value=2),
        end=CronSingleValueNumeric(value=9),
        interval=6,
    )
    assert parse_months_expr({"October-December/2"}) == CronRange(
        start=CronSingleValueNumeric(value=10),
        end=CronSingleValueNumeric(value=12),
        interval=2,
    )


def test_months_parser_parses_multiple_expressions() -> None:
    result = parse_months_expr({"3", "4-6"})
    assert isinstance(result, CronUnion)
    assert set(result.exprs) == {
        CronSingleValueNumeric(value=3),
        CronRange(
            start=CronSingleValueNumeric(value=4),
            end=CronSingleValueNumeric(value=6),
        ),
    }


def test_months_parser_errors_on_invalid() -> None:
    with raises(ValueError):
        parse_months_expr({"13"})
    with raises(ValueError):
        parse_months_expr({"befruary"})
    with raises(ValueError):
        parse_months_expr({"sup"})
    with raises(ValueError):
        parse_months_expr({"L"})
    with raises(ValueError):
        parse_months_expr({"3-L"})
    with raises(ValueError):
        parse_months_expr({"^-6"})
    with raises(ValueError):
        parse_months_expr({"L-2"})
    with raises(ValueError):
        parse_months_expr({""})
