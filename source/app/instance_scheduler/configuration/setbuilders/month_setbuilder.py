# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0


import calendar

from instance_scheduler.configuration.setbuilders.setbuilder import SetBuilder


class MonthSetBuilder(SetBuilder):
    """
    Class for building month sets, 1-12 ans jan-dec
    """

    def __init__(self, wrap: bool = True, ignorecase: bool = True) -> None:
        """
        Initializes set builder for month sets
        :param wrap: Set to True to allow wrapping at last month of the year
        :param ignorecase: Set to True to ignore case when mapping month names
        """
        SetBuilder.__init__(
            self,
            names=calendar.month_abbr[1:],
            significant_name_characters=3,
            offset=1,
            ignorecase=ignorecase,
            wrap=wrap,
        )
