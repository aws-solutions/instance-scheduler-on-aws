# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from datetime import datetime, timezone
from typing import Final
from zoneinfo import ZoneInfo

from instance_scheduler.model import (
    EC2SSMMaintenanceWindow,
    EC2SSMMaintenanceWindowStore,
)


def test_maint_win_store(maint_win_table: str) -> None:
    account_id = "111111111111"
    region = "us-east-1"
    window_name = "my-window"
    next_execution_time = datetime(year=2023, month=6, day=23, tzinfo=timezone.utc)
    duration = 1
    window_id = "mw-00000000000000000"
    schedule_timezone = "UTC"
    window: Final = EC2SSMMaintenanceWindow(
        account_id=account_id,
        region=region,
        window_id=window_id,
        window_name=window_name,
        schedule_timezone=ZoneInfo(schedule_timezone),
        next_execution_time=next_execution_time,
        duration_hours=duration,
    )

    store = EC2SSMMaintenanceWindowStore(maint_win_table)

    windows = list(store.get_ssm_windows_db(account=account_id, region=region))
    assert windows == []

    store.put_window_dynamodb(window)
    windows = list(store.get_ssm_windows_db(account=account_id, region=region))

    assert len(windows) == 1
    assert windows[0] == window

    store.delete_window(windows[0])

    windows = list(store.get_ssm_windows_db(account=account_id, region=region))
    assert windows == []
