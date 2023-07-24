# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import calendar
from typing import Optional

from instance_scheduler.configuration.setbuilders.setbuilder import SetBuilder


class MonthdaySetBuilder(SetBuilder):
    """
    Class for building sets of monthdays, 1-(28-31), ',', '-', '/", "*",  W for nearest weekday, L for last day of month
    """

    WILDCARD_WEEKDAY = "W"
    WILDCARD_LAST_WEEKDAY = "L"

    def __init__(self, year: int, month: int) -> None:
        """
        Initializes monthday set builder.
        :param year: Year of month to build sets for, only required for month aware 'W' and 'L' features in expressions
        :param month: Month to build sets for, only required for month aware 'W' and 'L' features in expressions
        """
        self.year = year
        self.month = month
        self._firstweekday, self._lastday = calendar.monthrange(year, month)

        SetBuilder.__init__(
            self,
            min_value=1,
            max_value=self._lastday,
            offset=1,
            ignorecase=False,
            wrap=False,
            last_item_wildcard=MonthdaySetBuilder.WILDCARD_LAST_WEEKDAY,
        )

        self._post_custom_parsers = [self._parse_weekday]

    def _parse_weekday(self, day_str: str) -> Optional[list[int]]:
        # dayW return working day nearest to day
        return self._get_weekday(day_str)

    def _parse_unknown(self, item: str) -> Optional[list[int]]:
        return [] if item in [str(d) for d in range(self.last, 32)] else None

    def _seperator_characters(self) -> str:
        # adding W to separator characters, it should not be formatted
        return SetBuilder._seperator_characters(self) + self.WILDCARD_WEEKDAY

    def _get_weekday(self, day_str: str) -> Optional[list[int]]:
        # returns working day nearest to day in month, string is in format dayW
        if (1 < len(day_str) <= 3) and day_str.endswith(self.WILDCARD_WEEKDAY):
            day = self._get_value_by_str(day_str[0:-1])
            if day is not None:
                # calculated day of week based on first weekday of month
                weekday = ((day % 7) + self._firstweekday - 1) % 7
                # for Saturdays use Friday, or Monday if it is the first day of the month
                if weekday == 5:
                    day = day - 1 if day > 1 else day + 2
                # for Sundays use next Monday, or Saturday if it is the last day of the month
                elif weekday == 6:
                    day = day + 1 if day < self._lastday else day - 2
                # for other days just return the specified day
                return [day]

        return None
