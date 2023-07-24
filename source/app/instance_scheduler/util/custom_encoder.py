# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import decimal
import json
from datetime import datetime
from typing import Any


class CustomEncoder(json.JSONEncoder):
    """
    Internal class used for serialization of types not supported in json.
    """

    def default(self, o: Any) -> Any:
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
