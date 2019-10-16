######################################################################################################################
#  Copyright 2019 Amazon.com, Inc. or its affiliates. All Rights Reserved.                                           #
#                                                                                                                    #
#  Licensed under the Apache License Version 2.0 (the "License"). You may not use this file except in compliance     #
#  with the License. A copy of the License is located at                                                             #
#                                                                                                                    #
#      http://www.apache.org/licenses/                                                                               #
#                                                                                                                    #
#  or in the "license" file accompanying this file. This file is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES #
#  OR CONDITIONS OF ANY KIND, express or implied. See the License for the specific language governing permissions    #
#  and limitations under the License.                                                                                #
######################################################################################################################

import calendar

from configuration.setbuilders.setbuilder import SetBuilder


class MonthdaySetBuilder(SetBuilder):
    """
    Class for building sets of monthdays, 1-(28-31), ',', '-', '/", "*",  W for nearest weekday, L for last day of month
    """
    WILDCARD_WEEKDAY = "W"
    WILDCARD_LAST_WEEKDAY = "L"

    def __init__(self, year, month):
        """
        Initializes monthday set builder.
        :param year: Year of month to build sets for, only required for month aware 'W' and 'L' features in expressions
        :param month: Month to build sets for, only required for month aware 'W' and 'L' features in expressions
        """
        self.year = year
        self.month = month
        self._firstweekday, self._lastday = calendar.monthrange(year, month)

        SetBuilder.__init__(self,
                            min_value=1,
                            max_value=self._lastday,
                            offset=1,
                            ignorecase=False,
                            wrap=False,
                            last_item_wildcard=MonthdaySetBuilder.WILDCARD_LAST_WEEKDAY)

        self._post_custom_parsers = [self._parse_weekday]

    def _parse_weekday(self, day_str):
        # dayW return working day nearest to day
        return self._get_weekday(day_str)

    def _parse_unknown(self, item):
        return [] if item in [str(d) for d in range(self.last, 32)] else None

    def _seperator_characters(self):
        # adding W to separator characters, it should not be formatted
        return SetBuilder._seperator_characters(self) + self.WILDCARD_WEEKDAY

    def _get_weekday(self, day_str):
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
