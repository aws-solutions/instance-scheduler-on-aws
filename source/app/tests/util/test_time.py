# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from instance_scheduler.util.time import is_aware


def test_is_aware() -> None:
    assert is_aware(datetime(year=2023, month=6, day=23, tzinfo=timezone.utc))
    assert is_aware(datetime(year=2023, month=6, day=23, tzinfo=ZoneInfo("Asia/Tokyo")))

    assert not is_aware(datetime(year=2023, month=6, day=23))
