# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import calendar

from pytest import raises

from instance_scheduler.configuration.setbuilders.weekday_setbuilder import (
    WeekdaySetBuilder,
)


# Documented behavior in the IG on 7/10/23
#
# Enter a comma-delimited list of days of the week, or a range of days of the week,
# during which the instance will run. For example, enter 0, 1, 2 or 0-2 to run an instance Monday through Wednesday.
# You can also enter multiple ranges. For example, enter 0-2, 4-6 to run an instance every day except Thursday.
#
# You can also schedule an instance to run every nth occurrence of a weekday in the month.
# For example, enter Mon#1 or 0#1 to run an instance the first Monday of the month.
#
# Enter a day and L to run an instance on the last occurrence of that weekday in the month.
# For example, enter friL or 4L to run an instance on the last Friday of the month.
def test_char_sentry_value_snapshot() -> None:
    assert WeekdaySetBuilder.WEEKDAY_NUMBER_CHAR == "#"
    assert WeekdaySetBuilder.LAST_DAY_WILDCARD == "L"


def test_day_names_and_abbreviations_map_correctly() -> None:
    # ie. mon, tue, wed
    for i, day_name in enumerate(calendar.day_abbr):
        print(f"{day_name} = {i}")
        assert WeekdaySetBuilder().build(day_name) == {i}

    for i, day_name in enumerate(calendar.day_name):
        print(f"{day_name} = {i}")
        assert WeekdaySetBuilder().build(day_name) == {i}


def test_providing_single_day_as_int_maps_correctly() -> None:
    # ie. 1, 3, 5
    for i in range(0, len(calendar.day_abbr) - 1):
        assert WeekdaySetBuilder().build(str(i)) == {i}


def test_weekday_numbered() -> None:
    for year in [2016, 2017]:
        for month in range(1, 13):
            weekday, days_in_month = calendar.monthrange(year, month)

            for day in range(1, days_in_month + 1):
                num = int((day - 1) / 7) + 1
                builder = WeekdaySetBuilder(year=year, month=month, day=day)

                tested_by_name = builder.build(
                    calendar.day_abbr[weekday] + "#" + str(num)
                )
                assert tested_by_name == {weekday}

                tested_by_value = builder.build(str(weekday) + "#" + str(num))
                assert tested_by_value == {weekday}

                for other_weekday in range(0, 7):
                    if other_weekday != weekday:
                        tested_by_name = builder.build(
                            calendar.day_abbr[other_weekday] + "#" + str(num)
                        )
                        assert tested_by_name == set()
                        tested_by_value = builder.build(
                            str(other_weekday) + "#" + str(num)
                        )
                        assert tested_by_value == set()

                for other_num in range(1, 6):
                    if num != other_num:
                        tested_by_name = builder.build(
                            calendar.day_abbr[weekday] + "#" + str(other_num)
                        )
                        assert tested_by_name == set()
                        tested_by_value = builder.build(
                            str(weekday) + "#" + str(other_num)
                        )
                        assert tested_by_value == set()

                weekday = (weekday + 1) % 7


def test_last_monday_returns_expected_day() -> None:
    # last 7 days of june 2023
    assert (
        WeekdaySetBuilder(year=2023, month=6, day=19).build("monL") == set()
    )  # 2nd-to-last monday
    assert WeekdaySetBuilder(year=2023, month=6, day=24).build("monL") == set()  # sat
    assert WeekdaySetBuilder(year=2023, month=6, day=25).build("monL") == set()  # sun
    assert WeekdaySetBuilder(year=2023, month=6, day=26).build("monL") == {0}  # mon
    assert WeekdaySetBuilder(year=2023, month=6, day=27).build("monL") == set()  # tue
    assert WeekdaySetBuilder(year=2023, month=6, day=28).build("monL") == set()  # wed
    assert WeekdaySetBuilder(year=2023, month=6, day=29).build("monL") == set()  # thur
    assert WeekdaySetBuilder(year=2023, month=6, day=30).build("monL") == set()  # fri


def test_last_tuesday_returns_expected_day() -> None:
    # last 7 days of june
    assert (
        WeekdaySetBuilder(year=2023, month=6, day=20).build("monL") == set()
    )  # 2nd-to-last tuesday
    assert WeekdaySetBuilder(year=2023, month=6, day=24).build("tueL") == set()  # sat
    assert WeekdaySetBuilder(year=2023, month=6, day=25).build("tueL") == set()  # sun
    assert WeekdaySetBuilder(year=2023, month=6, day=26).build("tueL") == set()  # mon
    assert WeekdaySetBuilder(year=2023, month=6, day=27).build("tueL") == {1}  # tue
    assert WeekdaySetBuilder(year=2023, month=6, day=28).build("tueL") == set()  # wed
    assert WeekdaySetBuilder(year=2023, month=6, day=29).build("tueL") == set()  # thur
    assert WeekdaySetBuilder(year=2023, month=6, day=30).build("tueL") == set()  # fri


def test_last_day_wildcard_on_all_days_in_year() -> None:
    for year in [2016, 2017]:
        for month in range(1, 13):
            weekday, days_in_month = calendar.monthrange(year, month)
            for tested_on_day in range(1, days_in_month + 1):
                builder = WeekdaySetBuilder(year=year, month=month, day=tested_on_day)

                # test by name of weekday
                day_num_l = calendar.day_abbr[weekday] + "L"
                tested_by_name = builder.build(day_num_l)
                # test by number of weekday
                day_value_l = str(weekday) + "L"
                tested_by_value = builder.build(day_value_l)

                # everything before last week should be empty set
                if tested_on_day <= (days_in_month - 7):
                    assert tested_by_name == set()
                    assert tested_by_value == set()

                else:
                    # in last week the set should contain the day
                    assert tested_by_name == {weekday}
                    assert tested_by_value == {weekday}

                    # test if ofther weekdays on that day return empty set
                    for d in range(0, 6):
                        if d != weekday:
                            day_num_l = calendar.day_abbr[d] + "L"
                            day_value_l = str(d) + "L"
                            assert builder.build(day_num_l) == set()
                            assert builder.build(day_value_l) == set()

                weekday = (weekday + 1) % 7


def test_last_xday_tag_throws_exception_when_current_date_not_provided() -> None:
    # L needs year, month and daya params
    with raises(ValueError):
        WeekdaySetBuilder().build("1L")


def test_nth_weekday_throws_exception_when_n_is_gte_6() -> None:
    # It is an oxymoron to ask for the 6th friday in the month as
    # there can only ever be at most 5 of a given day each month
    with raises(ValueError):
        WeekdaySetBuilder(year=2016, month=10, day=4).build("0#6")


def test_nth_weekday_throws_exception_when_n_is_lte_0() -> None:
    with raises(ValueError):
        WeekdaySetBuilder(year=2023, month=7, day=10).build("0#-1")
    with raises(ValueError):
        WeekdaySetBuilder(year=2016, month=10, day=4).build("0#0")
