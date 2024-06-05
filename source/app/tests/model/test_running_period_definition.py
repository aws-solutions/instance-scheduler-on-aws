# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from datetime import datetime

import pytest
from freezegun import freeze_time

from instance_scheduler.model.period_definition import (
    InvalidPeriodDefinition,
    PeriodDefinition,
)


def test_to_item_includes_all_values_when_provided() -> None:
    assert PeriodDefinition(
        name="test-period",
        begintime="05:00",
        endtime="22:00",
        weekdays={"mon-fri"},
        monthdays={"1-10"},
        months={"1-3"},
        description="some description",
        configured_in_stack="myStackName",
    ).to_item() == {
        "type": {"S": "period"},
        "name": {"S": "test-period"},
        "begintime": {"S": "05:00"},
        "endtime": {"S": "22:00"},
        "weekdays": {"SS": ["mon-fri"]},
        "monthdays": {"SS": ["1-10"]},
        "months": {"SS": ["1-3"]},
        "description": {"S": "some description"},
        "configured_in_stack": {"S": "myStackName"},
    }


def test_to_item_strips_empty_values() -> None:
    assert PeriodDefinition(name="test-period", begintime="00:00").to_item() == {
        "type": {"S": "period"},
        "name": {"S": "test-period"},
        "begintime": {"S": "00:00"},
    }


def test_to_item_from_item_round_trip_when_configured_in_stack() -> None:
    period = PeriodDefinition(
        name="test-period",
        begintime="05:00",
        endtime="22:00",
        weekdays={"mon-fri"},
        monthdays={"1-10"},
        months={"1-3"},
        description="some description",
        configured_in_stack="someStackName",
    )
    assert period == PeriodDefinition.from_item(period.to_item())


def test_to_item_from_item_round_trip_when_not_configured_in_stack() -> None:
    period = PeriodDefinition(
        name="test-period",
        begintime="05:00",
        endtime="22:00",
        weekdays={"mon-fri"},
        monthdays={"1-10"},
        months={"1-3"},
        description="some description",
    )
    assert period == PeriodDefinition.from_item(period.to_item())


def test_1_sided_period_is_valid() -> None:
    PeriodDefinition(name="test-period", begintime="10:00")
    PeriodDefinition(name="test-period", endtime="10:00")


def test_normal_period_is_valid() -> None:
    PeriodDefinition(name="test-period", begintime="10:00", endtime="20:00")


def test_specific_days_only_periods_are_valid() -> None:
    PeriodDefinition(name="test-period", weekdays={"mon-fri"})
    PeriodDefinition(name="test-period", monthdays={"1-3"})
    PeriodDefinition(name="test-period", months={"feb"})


@pytest.mark.parametrize(
    "valid_input", ["1", "12-15", "1/7", "1-15/2", "L", "20-L", "15W"]
)
def test_does_not_error_on_valid_monthday(valid_input: str) -> None:
    PeriodDefinition(name="test-period", monthdays={valid_input})


def test_does_not_error_on_multipart_monthday() -> None:
    PeriodDefinition(name="test-period", monthdays={"1", "2", "1/8"})


@freeze_time(datetime(2023, 2, 25, 0, 0, 0))
@pytest.mark.parametrize("valid_input", ["30", "26-30", "L"])
def test_does_not_error_in_feb(valid_input: str) -> None:
    PeriodDefinition(name="test-period", monthdays={valid_input})


@pytest.mark.parametrize("invalid_input", ["W", "32", "bad-string", "20-15"])
def test_errors_on_invalid_monthday(invalid_input: str) -> None:
    with pytest.raises(InvalidPeriodDefinition):
        PeriodDefinition(name="test-period", monthdays={invalid_input})


@pytest.mark.parametrize(
    "valid_input",
    ["1", "10-12", "1/3", "5-9/2", "Jan", "Jan-Jul", "mar/3", "Jan-Jul/2"],
)
def test_does_not_error_on_valid_month(valid_input: str) -> None:
    PeriodDefinition(name="test-period", months={valid_input})


def test_does_not_error_on_multipart_month() -> None:
    PeriodDefinition(name="test-period", months={"1", "Feb", "Mar-May"})


@pytest.mark.parametrize("invalid_input", ["0", "13", "not-a-month", "W", "L"])
def test_errors_on_invalid_month(invalid_input: str) -> None:
    with pytest.raises(InvalidPeriodDefinition):
        PeriodDefinition(name="test-period", months={invalid_input})


@pytest.mark.parametrize(
    "valid_input",
    [
        "1",
        "4-6",
        "1-2, Thu-Fri",
        "0#1",
        "Mon#1",
        "Mon#5",
        "FriL",
        "6L",
        "SUN",
    ],
)
def test_does_not_error_on_valid_weekday(valid_input: str) -> None:
    PeriodDefinition(name="test-period", weekdays={valid_input})


def test_does_not_error_on_multipart_weekday() -> None:
    PeriodDefinition(name="test-period", weekdays={"1", "2-3", "fri"})


@pytest.mark.parametrize("invalid_input", ["-1", "7", "not-a-day", "Mon#6", "2-L"])
def test_errors_on_invalid_weekday(invalid_input: str) -> None:
    with pytest.raises(InvalidPeriodDefinition):
        PeriodDefinition(name="test-period", weekdays={invalid_input})


def test_throws_exception_when_begintime_is_after_endtime() -> None:
    with pytest.raises(InvalidPeriodDefinition):
        PeriodDefinition(name="test-period", begintime="10:00", endtime="5:00")


def test_throws_exception_when_no_period_values_provided() -> None:
    with pytest.raises(InvalidPeriodDefinition):
        PeriodDefinition(name="test-period")


@pytest.mark.parametrize("valid_time", ["00:00", "01:05", "23:59", "4:35"])
def test_accepts_valid_time_strings(valid_time: str) -> None:
    PeriodDefinition(name="test-period", begintime=valid_time)
    PeriodDefinition(name="test-period", endtime=valid_time)


@pytest.mark.parametrize("invalid_time", ["25:00", "ab", "24:00", "24:01"])
def test_rejects_invalid_time_strings(invalid_time: str) -> None:
    with pytest.raises(InvalidPeriodDefinition):
        PeriodDefinition(name="test-period", begintime=invalid_time)
        PeriodDefinition(name="test-period", endtime=invalid_time)
