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

import decimal
import json
from datetime import datetime


class CustomEncoder(json.JSONEncoder):
    """
    Internal class used for serialization of types not supported in json.
    """

    def default(self, o): # pylint: disable=E0202
        # sets become lists
        if isinstance(o, set):
            return list(o)
        # datetimes become strings
        if isinstance(o, datetime):
            return o.isoformat()
        if isinstance(o, decimal.Decimal):
            return float(o)
        if isinstance(o, type):
            return str(o)

        return json.JSONEncoder.default(self, o)


