# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from datetime import datetime


def is_aware(dt: datetime) -> bool:
    """
    Returns `True` if the `datetime` is timezone-aware.

    [[Documentation] Determining if an Object is Aware or Naive](https://docs.python.org/3/library/datetime.html#determining-if-an-object-is-aware-or-naive)
    """
    return dt.tzinfo is not None and dt.tzinfo.utcoffset(dt) is not None
