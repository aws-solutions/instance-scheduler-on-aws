# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from datetime import datetime, timezone
from typing import TYPE_CHECKING
from unittest.mock import ANY

from boto3 import Session

from instance_scheduler.model import EC2SSMMaintenanceWindowStore
from tests.logger import MockLogger

if TYPE_CHECKING:
    from mypy_boto3_ssm.type_defs import MaintenanceWindowIdentityTypeDef
else:
    MaintenanceWindowIdentityTypeDef = object


def test_maint_win_store(maint_win_table: str) -> None:
    account_id = "111111111111"
    region = "us-east-1"
    window_name = "my-window"
    next_execution_time = datetime(year=2023, month=6, day=23, tzinfo=timezone.utc)
    duration = 1
    window_id = "mw-00000000000000000"
    schedule_timezone = "UTC"
    format_string = "%Y-%m-%dT%H:%M%z"
    window: MaintenanceWindowIdentityTypeDef = {
        "Name": window_name,
        "NextExecutionTime": next_execution_time.strftime(format_string),
        "Duration": duration,
        "WindowId": window_id,
        "ScheduleTimezone": schedule_timezone,
    }

    store = EC2SSMMaintenanceWindowStore(
        session=Session(), table_name=maint_win_table, logger=MockLogger()
    )

    windows = store.get_ssm_windows_db(account=account_id, region=region)
    assert windows == []

    store.put_window_dynamodb(window=window, account=account_id, region=region)
    windows = store.get_ssm_windows_db(account=account_id, region=region)

    assert len(windows) == 1
    account_region = f"{account_id}:{region}"
    assert windows[0] == {
        "account-region": account_region,
        "Name": window_name,
        "Duration": duration,
        "WindowId": window_id,
        "TimeToLive": ANY,
        "NextExecutionTime": next_execution_time.strftime(format_string),
        "ScheduleTimezone": schedule_timezone,
    }

    window["account-region"] = account_region  # type: ignore[typeddict-unknown-key]
    store.delete_window(window)

    windows = store.get_ssm_windows_db(account=account_id, region=region)
    assert windows == []
