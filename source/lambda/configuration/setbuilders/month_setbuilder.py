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


class MonthSetBuilder(SetBuilder):
    """
    Class for building month sets, 1-12 ans jan-dec
    """

    def __init__(self, wrap=True, ignorecase=True):
        """
        Initializes set builder for month sets
        :param wrap: Set to True to allow wrapping at last month of the year
        :param ignorecase: Set to True to ignore case when mapping month names
        """
        SetBuilder.__init__(self,
                            names=calendar.month_abbr[1:],
                            significant_name_characters=3,
                            offset=1,
                            ignorecase=ignorecase,
                            wrap=wrap)
