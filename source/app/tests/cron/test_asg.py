# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from pytest import raises

from instance_scheduler.cron.asg import (
    to_asg_expr_monthdays,
    to_asg_expr_months,
    to_asg_expr_weekdays,
)
from instance_scheduler.cron.expression import (
    CronAll,
    CronRange,
    CronSingleValueNumeric,
)
from instance_scheduler.cron.parser import (
    parse_monthdays_expr,
    parse_months_expr,
    parse_weekdays_expr,
)


def test_to_asg_expr_months() -> None:
    assert to_asg_expr_months(CronAll()) == "*"
    assert to_asg_expr_months(CronSingleValueNumeric(value=3)) == "mar"
    assert to_asg_expr_months(CronSingleValueNumeric(value=7)) == "jul"
    assert (
        to_asg_expr_months(
            CronRange(
                start=CronSingleValueNumeric(value=2),
                end=CronSingleValueNumeric(value=9),
            )
        )
        == "feb-sep"
    )


def test_e2e_months() -> None:
    assert to_asg_expr_months(parse_months_expr({"*"})) == "*"
    assert to_asg_expr_months(parse_months_expr({"?"})) == "*"

    assert to_asg_expr_months(parse_months_expr({"jan"})) == "jan"
    assert to_asg_expr_months(parse_months_expr({"February"})) == "feb"
    assert to_asg_expr_months(parse_months_expr({"July"})) == "jul"

    assert to_asg_expr_months(parse_months_expr({"3"})) == "mar"
    assert to_asg_expr_months(parse_months_expr({"6"})) == "jun"

    assert to_asg_expr_months(parse_months_expr({"3-8"})) == "mar-aug"
    assert to_asg_expr_months(parse_months_expr({"5-12"})) == "may-dec"

    assert to_asg_expr_months(parse_months_expr({"jun-nov"})) == "jun-nov"
    assert to_asg_expr_months(parse_months_expr({"April-February"})) == "apr-feb"
    assert to_asg_expr_months(parse_months_expr({"7-1"})) == "jul-jan"

    assert to_asg_expr_months(parse_months_expr({"4/2"})) == "apr/2"
    assert to_asg_expr_months(parse_months_expr({"2-9/3"})) == "feb-sep/3"
    assert to_asg_expr_months(parse_months_expr({"Jun-Oct/5"})) == "jun-oct/5"
    assert to_asg_expr_months(parse_months_expr({"January-August/3"})) == "jan-aug/3"

    assert to_asg_expr_months(parse_months_expr({"7-2/3"})) == "jul-feb/3"
    assert to_asg_expr_months(parse_months_expr({"nov-jun/4"})) == "nov-jun/4"
    assert to_asg_expr_months(parse_months_expr({" October-April/ 3  "})) == "oct-apr/3"

    assert set(
        to_asg_expr_months(
            parse_months_expr({"jul,sep", "Oct-Dec/2", "feb-mar"})
        ).split(",")
    ) == {"jul", "sep", "oct-dec/2", "feb-mar"}


def test_e2e_monthdays() -> None:
    assert to_asg_expr_monthdays(parse_monthdays_expr({"*"})) == "*"
    assert to_asg_expr_monthdays(parse_monthdays_expr({"?"})) == "*"

    assert to_asg_expr_monthdays(parse_monthdays_expr({"3"})) == "3"
    assert to_asg_expr_monthdays(parse_monthdays_expr({"6"})) == "6"

    assert to_asg_expr_monthdays(parse_monthdays_expr({"3-8"})) == "3-8"

    assert to_asg_expr_monthdays(parse_monthdays_expr({"L"})) == "L"
    assert to_asg_expr_monthdays(parse_monthdays_expr({"4-L"})) == "4-L"

    assert to_asg_expr_monthdays(parse_monthdays_expr({"4/2"})) == "4/2"
    assert to_asg_expr_monthdays(parse_monthdays_expr({"3-9/3"})) == "3-9/3"
    assert to_asg_expr_monthdays(parse_monthdays_expr({"16-L/4"})) == "16-L/4"

    assert set(
        to_asg_expr_monthdays(parse_monthdays_expr({"3,6", "10-15/2", "22-23"})).split(
            ","
        )
    ) == {"3", "6", "10-15/2", "22-23"}

    with raises(NotImplementedError):
        to_asg_expr_monthdays(parse_monthdays_expr({"15,L,5W"}))


def test_e2e_weekdays() -> None:
    assert to_asg_expr_weekdays(parse_weekdays_expr({"*"})) == "*"
    assert to_asg_expr_weekdays(parse_weekdays_expr({"?"})) == "*"

    assert to_asg_expr_weekdays(parse_weekdays_expr({"mon"})) == "mon"
    assert to_asg_expr_weekdays(parse_weekdays_expr({"Tuesday"})) == "tue"
    assert to_asg_expr_weekdays(parse_weekdays_expr({"Saturday"})) == "sat"

    assert to_asg_expr_weekdays(parse_weekdays_expr({"3"})) == "thu"
    assert to_asg_expr_weekdays(parse_weekdays_expr({"6"})) == "sun"

    assert to_asg_expr_weekdays(parse_weekdays_expr({"3-6"})) == "thu-sun"
    assert to_asg_expr_weekdays(parse_weekdays_expr({"1-3"})) == "tue-thu"

    assert to_asg_expr_weekdays(parse_weekdays_expr({"tue-thu"})) == "tue-thu"
    assert to_asg_expr_weekdays(parse_weekdays_expr({"Monday-Friday"})) == "mon-fri"

    assert to_asg_expr_weekdays(parse_weekdays_expr({"4-2"})) == "fri-wed"
    assert to_asg_expr_weekdays(parse_weekdays_expr({"sat-mon"})) == "sat-mon"

    assert to_asg_expr_weekdays(parse_weekdays_expr({"4/2"})) == "fri/2"
    assert to_asg_expr_weekdays(parse_weekdays_expr({"0-4/3"})) == "mon-fri/3"
    assert to_asg_expr_weekdays(parse_weekdays_expr({"Tue-Sun/3"})) == "tue-sun/3"
    assert to_asg_expr_weekdays(parse_weekdays_expr({"Monday-Friday/5"})) == "mon-fri/5"

    assert to_asg_expr_weekdays(parse_weekdays_expr({"6-2/3"})) == "sun-wed/3"
    assert to_asg_expr_weekdays(parse_weekdays_expr({"fri-wed/3"})) == "fri-wed/3"
    assert (
        to_asg_expr_weekdays(parse_weekdays_expr({" Saturday-Thursday/ 2  "}))
        == "sat-thu/2"
    )

    assert set(
        to_asg_expr_weekdays(
            parse_weekdays_expr({"0,thu", "Wednesday-Friday/2", "sat-sun"})
        ).split(",")
    ) == {"mon", "thu", "wed-fri/2", "sat-sun"}

    with raises(NotImplementedError):
        to_asg_expr_weekdays(parse_weekdays_expr({"Mon#3"}))

    with raises(NotImplementedError):
        to_asg_expr_weekdays(parse_weekdays_expr({"Wednesday#2"}))

    with raises(NotImplementedError):
        to_asg_expr_weekdays(parse_weekdays_expr({"3#1"}))

    with raises(NotImplementedError):
        to_asg_expr_weekdays(parse_weekdays_expr({"satL"}))

    with raises(NotImplementedError):
        to_asg_expr_weekdays(parse_weekdays_expr({"ThursdayL"}))

    with raises(NotImplementedError):
        to_asg_expr_weekdays(parse_weekdays_expr({"2L"}))
