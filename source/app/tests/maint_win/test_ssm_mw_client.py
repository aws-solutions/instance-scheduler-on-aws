# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from datetime import datetime, timedelta
from typing import Final
from zoneinfo import ZoneInfo

from freezegun import freeze_time

from instance_scheduler.model.maint_win import EC2SSMMaintenanceWindow

# use common UTC zoneinfo in these tests to allow proper emulation of SSM API
utc_timezone: Final = ZoneInfo("Etc/UTC")
account_id: Final = "123456789012"
region: Final = "us-east-1"


def test_window_currently_running() -> None:
    next_execution_time: Final = datetime(
        year=2023, month=11, day=6, hour=15, minute=14, tzinfo=utc_timezone
    )
    duration_hours: Final = 1

    window: Final = EC2SSMMaintenanceWindow(
        account_id="111111111111",
        region="us-east-1",
        schedule_timezone=utc_timezone,
        window_id="mw-00000000000000000",
        window_name="mon-1",
        duration_hours=duration_hours,
        next_execution_time=next_execution_time,
    )

    end: Final = next_execution_time + timedelta(hours=duration_hours)

    for dt in (
        next_execution_time - timedelta(minutes=20),
        end,
        end + timedelta(minutes=1),
    ):
        with freeze_time(dt):
            assert not window.is_running_at(dt, scheduler_interval_minutes=5)
    for dt in (
        next_execution_time,
        next_execution_time - timedelta(minutes=10),  # 10 minute early start
        next_execution_time + timedelta(minutes=1),
        end - timedelta(minutes=1),
    ):
        with freeze_time(dt):
            assert window.is_running_at(dt, scheduler_interval_minutes=5)
