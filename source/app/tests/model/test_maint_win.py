# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from dataclasses import replace
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Final
from zoneinfo import ZoneInfo

from dateutil.parser import isoparse
from pytest import raises

from instance_scheduler.model import (
    EC2SSMMaintenanceWindow,
    EC2SSMMaintenanceWindowValidationError,
)

if TYPE_CHECKING:
    from mypy_boto3_dynamodb.type_defs import GetItemOutputTypeDef
    from mypy_boto3_ssm.type_defs import MaintenanceWindowIdentityTypeDef
else:
    GetItemOutputTypeDef = object
    MaintenanceWindowIdentityTypeDef = object


def example_maint_win() -> EC2SSMMaintenanceWindow:
    return EC2SSMMaintenanceWindow(
        account_id="111111111111",
        region="us-east-1",
        window_id="mw-00000000000000000",
        window_name="my-window",
        schedule_timezone=ZoneInfo("UTC"),
        next_execution_time=datetime(year=2023, month=6, day=23, tzinfo=timezone.utc),
        duration=1,
    )


def test_validate_account_id() -> None:
    invalid_account_ids: Final = (
        "",
        "invalid",
        "00000000000",
        "0000000000000",
        " 000000000000",
    )
    for invalid_account_id in invalid_account_ids:
        with raises(EC2SSMMaintenanceWindowValidationError):
            replace(example_maint_win(), account_id=invalid_account_id)


def test_validate_region() -> None:
    with raises(EC2SSMMaintenanceWindowValidationError):
        replace(example_maint_win(), region="")


def test_validate_window_id() -> None:
    invalid_window_ids: Final = (
        "",
        "invalid",
        "mw-0000000000000000",
        "mw-000000000000000000",
        "mw-00000000000000000 ",
    )
    for invalid_window_id in invalid_window_ids:
        with raises(EC2SSMMaintenanceWindowValidationError):
            replace(example_maint_win(), window_id=invalid_window_id)


def test_validate_window_name() -> None:
    invalid_window_names: Final = (
        "",
        "mw",
        "invalid-@",
        "  otherwise-valid",
        "a" * 129,
    )
    for invalid_window_name in invalid_window_names:
        with raises(EC2SSMMaintenanceWindowValidationError):
            replace(example_maint_win(), window_name=invalid_window_name)


def test_validate_next_execution_time() -> None:
    with raises(EC2SSMMaintenanceWindowValidationError):
        # utcnow returns a naive datetime
        replace(example_maint_win(), next_execution_time=datetime.utcnow())


def test_validate_duration() -> None:
    invalid_durations: Final = (0, -10, 30)
    for invalid_duration in invalid_durations:
        with raises(EC2SSMMaintenanceWindowValidationError):
            replace(example_maint_win(), duration=invalid_duration)


def test_to_item() -> None:
    account_id = "111111111111"
    region = "us-east-1"
    window_id = "mw-00000000000000000"
    window_name = "my-window"
    schedule_timezone = "Europe/Amsterdam"
    next_execution_time = datetime(
        year=2023, month=6, day=23, tzinfo=ZoneInfo(schedule_timezone)
    )
    duration = 1
    maint_win = EC2SSMMaintenanceWindow(
        account_id=account_id,
        region=region,
        window_id=window_id,
        window_name=window_name,
        schedule_timezone=ZoneInfo(schedule_timezone),
        next_execution_time=next_execution_time,
        duration=duration,
    )
    assert maint_win.to_item() == {
        "account-region": {"S": f"{account_id}:{region}"},
        "WindowId": {"S": window_id},
        "Name": {"S": window_name},
        "ScheduleTimezone": {"S": schedule_timezone},
        "NextExecutionTime": {"S": next_execution_time.isoformat()},
        "Duration": {"N": str(duration)},
    }


def test_to_key() -> None:
    account_id = "111111111111"
    region = "us-east-1"
    window_name = "my-window"
    window = replace(
        example_maint_win(),
        account_id=account_id,
        region=region,
        window_name=window_name,
    )
    assert window.to_key() == {
        "account-region": f"{account_id}:{region}",
        "Name": window_name,
    }


def test_from_identity() -> None:
    account_id = "111111111111"
    region = "us-east-1"
    window_id = "mw-00000000000000000"
    window_name = "my-window"
    schedule_timezone = "Asia/Tokyo"
    next_execution_time = datetime(
        year=2023, month=6, day=23, tzinfo=ZoneInfo(schedule_timezone)
    )
    duration = 1
    identity: MaintenanceWindowIdentityTypeDef = {
        "WindowId": window_id,
        "Name": window_name,
        "ScheduleTimezone": schedule_timezone,
        "NextExecutionTime": next_execution_time.isoformat(),
        "Duration": duration,
    }
    maint_win = EC2SSMMaintenanceWindow.from_identity(
        identity=identity, account_id=account_id, region=region
    )
    assert maint_win.account_id == account_id
    assert maint_win.region == region
    assert maint_win.window_id == window_id
    assert maint_win.window_name == window_name
    assert maint_win.schedule_timezone == ZoneInfo(schedule_timezone)
    assert maint_win.next_execution_time == next_execution_time
    assert maint_win.duration == duration


def test_from_identity_no_timezone() -> None:
    next_execution_time = datetime(year=2023, month=6, day=23, tzinfo=timezone.utc)
    identity: MaintenanceWindowIdentityTypeDef = {
        "WindowId": "mw-00000000000000000",
        "Name": "my-window",
        "NextExecutionTime": next_execution_time.isoformat(),
        "Duration": 1,
    }
    maint_win = EC2SSMMaintenanceWindow.from_identity(
        identity=identity, account_id="111111111111", region="us-east-1"
    )
    assert maint_win.schedule_timezone == ZoneInfo("UTC")
    assert maint_win.next_execution_time == next_execution_time


def test_from_identity_utc_offset_shorthand() -> None:
    next_execution_time = "2023-06-24T00:00Z"
    identity: MaintenanceWindowIdentityTypeDef = {
        "WindowId": "mw-00000000000000000",
        "Name": "my-window",
        "NextExecutionTime": next_execution_time,
        "Duration": 1,
    }
    maint_win = EC2SSMMaintenanceWindow.from_identity(
        identity=identity, account_id="111111111111", region="us-east-1"
    )
    assert maint_win.schedule_timezone == ZoneInfo("UTC")
    assert maint_win.next_execution_time == isoparse(next_execution_time)


def test_from_item() -> None:
    account_id = "111111111111"
    region = "us-east-1"
    window_id = "mw-00000000000000000"
    window_name = "my-window"
    schedule_timezone = "Asia/Tokyo"
    next_execution_time = datetime(
        year=2023, month=6, day=23, tzinfo=ZoneInfo(schedule_timezone)
    )
    duration = 1
    item: GetItemOutputTypeDef = {
        "Item": {
            "account-region": {"S": f"{account_id}:{region}"},
            "Name": {"S": window_name},
            "WindowId": {"S": window_id},
            "ScheduleTimezone": {"S": schedule_timezone},
            "NextExecutionTime": {"S": next_execution_time.isoformat()},
            "Duration": {"N": str(duration)},
        },
        "ConsumedCapacity": {},
        "ResponseMetadata": {
            "RequestId": "",
            "HostId": "",
            "HTTPStatusCode": 200,
            "HTTPHeaders": {},
            "RetryAttempts": 0,
        },
    }
    maint_win = EC2SSMMaintenanceWindow.from_item(item)
    assert maint_win.account_id == account_id
    assert maint_win.region == region
    assert maint_win.window_id == window_id
    assert maint_win.window_name == window_name
    assert maint_win.schedule_timezone == ZoneInfo(schedule_timezone)
    assert maint_win.next_execution_time == next_execution_time
    assert maint_win.duration == duration
