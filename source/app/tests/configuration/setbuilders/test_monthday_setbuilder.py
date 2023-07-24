# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import calendar

from pytest import raises

from instance_scheduler.configuration.setbuilders.monthday_setbuilder import (
    MonthdaySetBuilder,
)


# Documented behavior in the IG on 7/10/23
#
# Enter a comma-delimited list of days of the month, or a hyphenated range of days, during which the instance will run.
# For example, enter 1, 2, 3 or 1-3 to run an instance during the first three days of the month.
# You can also enter multiple ranges.
# For example, enter 1-3, 7-9 to run an instance from the 1st to the 3rd and the 7th through the 9th.
#
# You can also schedule an instance to run every nth day of the month or every nth day of the month in a range.
# For example, enter 1/7 to run an instance every seventh day starting on the 1st.
# Enter 1-15/2 to run an instance every other day from the 1st to the 15th.
#
# Enter L to run an instance on the last day of the month.
# Enter a date and W to run an instance on the nearest weekday to the specified date.
# For example, enter 15W to run an instance on the nearest weekday to the 15th.
def test_single_day_by_integer() -> None:
    years = [2016, 2017]  # leap and normal year

    for year in years:
        for month in range(1, 13):
            _, days = calendar.monthrange(year, month)

            for day in range(1, days):
                assert MonthdaySetBuilder(year, month).build(str(day)) == {day}


def test_single_range() -> None:
    assert MonthdaySetBuilder(2023, 7).build("5-9") == {5, 6, 7, 8, 9}


def test_multiple_ranges() -> None:
    assert MonthdaySetBuilder(2023, 7).build("13-15, 26-27, 29") == {
        13,
        14,
        15,
        26,
        27,
        29,
    }


def test_every_nth_day() -> None:
    assert MonthdaySetBuilder(2023, 7).build("1/7") == {1, 8, 15, 22, 29}
    assert MonthdaySetBuilder(2023, 7).build("5/14") == {5, 19}


def test_every_n_days_in_range() -> None:
    assert MonthdaySetBuilder(2023, 7).build("1-10/2") == {1, 3, 5, 7, 9}
    assert MonthdaySetBuilder(2023, 7).build("15-30/3") == {15, 18, 21, 24, 27, 30}


def test_L_wildcard_returns_last_day_of_each_month() -> None:
    years = [2016, 2017]  # leap and normal year

    for year in years:
        for month in range(1, 13):
            _, days = calendar.monthrange(year, month)
            assert MonthdaySetBuilder(year, month).build("L") == {days}


def test_W_wildcard_returns_nearest_weekday_in_same_month() -> None:
    years = [2016, 2017]  # leap and normal year

    for year in years:
        for month in range(1, 13):
            _, days = calendar.monthrange(year, month)

            for day in range(1, days):
                weekday = calendar.weekday(year, month, day)
                result = day
                if (
                    weekday == 5
                ):  # Saturdays return the prev friday unless doing so would be a diff month
                    result = day - 1 if day > 1 else day + 2
                elif (
                    weekday == 6
                ):  # Sundays return the next monday unless doing so would be a diff month
                    result = day + 1 if day < days else day - 2

                assert MonthdaySetBuilder(year, month).build(str(day) + "W") == {result}


def test_exceptions() -> None:
    for h in range(13, 25):
        with raises(ValueError):
            MonthdaySetBuilder(2016, 1).build("W")
        with raises(ValueError):
            MonthdaySetBuilder(2016, 1).build("32W")
