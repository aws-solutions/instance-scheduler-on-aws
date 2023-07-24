# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import calendar

from instance_scheduler.configuration.setbuilders.month_setbuilder import (
    MonthSetBuilder,
)


def test_month_names() -> None:
    # abbreviations, case-insensitive
    for i, name in enumerate(calendar.month_abbr[1:]):
        assert MonthSetBuilder().build(name) == {i + 1}
        assert MonthSetBuilder().build(name.lower()) == {i + 1}
        assert MonthSetBuilder().build(name.upper()) == {i + 1}

    # full names, case-insensitive
    for i, name in enumerate(calendar.month_name[1:]):
        assert MonthSetBuilder().build(name) == {i + 1}
        assert MonthSetBuilder().build(name.lower()) == {i + 1}
        assert MonthSetBuilder().build(name.upper()) == {i + 1}


def test_months_as_integers() -> None:
    for i in range(1, 13):  # 13 is exclusive, so this is 1-12
        assert MonthSetBuilder().build(str(i)) == {i}
