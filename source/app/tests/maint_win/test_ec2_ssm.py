# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from datetime import time
from typing import Any, Final
from unittest.mock import MagicMock, patch

from boto3.session import Session
from freezegun import freeze_time
from pytest_mock import MockFixture

from instance_scheduler.maint_win import EC2SSMMaintenanceWindows
from tests.logger import MockLogger

next_execution_time: Final = "2020-04-09T19:00Z"


def test_ssm_maintenance_windows_1(mocker: MockFixture) -> None:
    window_list = [
        {
            "WindowId": "mw-018e7137c74304cb5",
            "Name": "mon-1",
            "Enabled": True,
            "Duration": 1,
            "Cutoff": 0,
            "Schedule": "cron(0 0 19 ? * * *)",
            "NextExecutionTime": next_execution_time,
        }
    ]
    maint_win: Any = EC2SSMMaintenanceWindows(
        hub_session=Session(),
        spoke_session=Session(),
        spoke_account_id="111111111111",
        table_name="maint-win-table",
        scheduler_interval=10,
        logger=MockLogger(),
    )
    mocker.patch.object(maint_win, "get_ssm_windows")
    maint_win.get_ssm_windows.return_value = window_list
    session = ""
    account = "1111"
    region = "us-east-1"

    response = maint_win.ssm_maintenance_windows(session, account, region)

    assert response["mon-1"].periods[0]["period"].name == "mon-1-period"
    assert response["mon-1"].periods[0]["period"].begintime == time(18, 40)
    assert response["mon-1"].periods[0]["period"].endtime == time(20, 0)
    assert response["mon-1"].periods[0]["period"].months == {4}
    assert response["mon-1"].periods[0]["period"].monthdays == {9}


def test_ssm_maintenance_windows_2(mocker: MockFixture) -> None:
    window_list = [
        {
            "WindowId": "mw-018e7137c74304cb5",
            "Name": "mon-1",
            "Enabled": True,
            "Duration": 1,
            "Cutoff": 0,
            "Schedule": "cron(0 0 19 ? * * *)",
            "NextExecutionTime": "2020-05-10T15:00Z",
        }
    ]
    maint_win: Any = EC2SSMMaintenanceWindows(
        hub_session=Session(),
        spoke_session=Session(),
        spoke_account_id="111111111111",
        table_name="maint-win-table",
        scheduler_interval=10,
        logger=MockLogger(),
    )
    mocker.patch.object(maint_win, "get_ssm_windows")
    maint_win.get_ssm_windows.return_value = window_list
    session = ""
    account = "1111"
    region = "us-east-1"
    response = maint_win.ssm_maintenance_windows(session, account, region)

    assert response["mon-1"].periods[0]["period"].name == "mon-1-period"
    assert response["mon-1"].periods[0]["period"].begintime == time(14, 40)
    assert response["mon-1"].periods[0]["period"].endtime == time(16, 0)
    assert response["mon-1"].periods[0]["period"].months == {5}
    assert response["mon-1"].periods[0]["period"].monthdays == {10}


@freeze_time("2020-05-10 15:30:34")
def test_check_window_running_1() -> None:
    window = {
        "WindowId": "mw-018e7137c74304cb5",
        "Name": "mon-1",
        "Enabled": True,
        "Duration": 1,
        "Cutoff": 0,
        "Schedule": "cron(0 10 19 ? * * *)",
        "NextExecutionTime": "2020-05-10T15:00Z",
    }
    mw = EC2SSMMaintenanceWindows(
        hub_session=Session(),
        spoke_session=Session(),
        spoke_account_id="",
        table_name="",
        scheduler_interval=5,
        logger=MockLogger(),
    )
    assert mw.check_window_running(window)


@freeze_time("2020-05-11 15:30:34")
def test_check_window_running_2() -> None:
    window = {
        "WindowId": "mw-018e7137c74304cb5",
        "Name": "mon-1",
        "Enabled": True,
        "Duration": 1,
        "Cutoff": 0,
        "Schedule": "cron(0 10 19 ? * * *)",
        "NextExecutionTime": "2020-05-10T15:00Z",
    }
    mw = EC2SSMMaintenanceWindows(
        hub_session=Session(),
        spoke_session=Session(),
        spoke_account_id="",
        table_name="",
        scheduler_interval=5,
        logger=MockLogger(),
    )
    assert not mw.check_window_running(window)


@patch("instance_scheduler.maint_win.ec2_ssm.EC2SSMMaintenanceWindowStore")
def test_get_ssm_windows(mock_store: MagicMock) -> None:
    window_list = [
        {
            "WindowId": "mw-018e7137c74304cb5",
            "Name": "mon-1",
            "Duration": 1,
            "NextExecutionTime": next_execution_time,
        }
    ]
    maint_win: Any = EC2SSMMaintenanceWindows(
        hub_session=Session(),
        spoke_session=Session(),
        spoke_account_id="111111111111",
        table_name="maint-win-table",
        scheduler_interval=10,
        logger=MockLogger(),
    )
    mock_store.return_value.get_ssm_windows_db.return_value = window_list

    session = ""
    account = "1111"
    region = "us-east-1"
    with patch.object(maint_win, "get_ssm_windows_service"), patch.object(
        maint_win, "process_ssm_window"
    ):
        response = maint_win.get_ssm_windows(session, account, region)

    assert response == window_list


@patch("instance_scheduler.maint_win.ec2_ssm.EC2SSMMaintenanceWindowStore")
def test_process_ssm_window_1(mock_store: MagicMock) -> None:
    ssm_windows_db = [
        {
            "WindowId": "mw-018e7137c74304cb5",
            "Name": "mon-1",
            "Duration": 1,
            "NextExecutionTime": next_execution_time,
        },
        {
            "WindowId": "mw-018e7137c74304wb5",
            "Name": "mon-2",
            "Duration": 1,
            "NextExecutionTime": "2020-04-10T19:00Z",
        },
    ]
    window = {
        "WindowId": "mw-018e7137c74304cb5",
        "Name": "mon-1",
        "Duration": 1,
        "NextExecutionTime": next_execution_time,
    }
    maint_win: Any = EC2SSMMaintenanceWindows(
        hub_session=Session(),
        spoke_session=Session(),
        spoke_account_id="111111111111",
        table_name="maint-win-table",
        scheduler_interval=10,
        logger=MockLogger(),
    )
    account = "1111"
    region = "us-east-1"
    maint_win.process_ssm_window(
        window=window, ssm_windows_db=ssm_windows_db, account=account, region=region
    )
    mock_store.return_value.put_window_dynamodb.assert_called_with(
        window=window, account=account, region=region
    )


@patch("instance_scheduler.maint_win.ec2_ssm.EC2SSMMaintenanceWindowStore")
def test_process_ssm_window_2(mock_store: MagicMock) -> None:
    ssm_windows_db = [
        {
            "WindowId": "mw-018e7137c74304cb5",
            "Name": "mon-1",
            "Enabled": True,
            "Duration": 1,
            "Cutoff": 0,
            "Schedule": "cron(0 10 19 ? * * *)",
            "NextExecutionTime": next_execution_time,
        },
        {
            "WindowId": "mw-018e7137c74304wb5",
            "Name": "mon-2",
            "Enabled": False,
            "Duration": 1,
            "Cutoff": 0,
            "Schedule": "cron(0 10 19 ? * * *)",
            "NextExecutionTime": "2020-04-10T19:00Z",
        },
    ]
    window = {
        "WindowId": "mw-018e7137c74304cb5",
        "Name": "mon-3",
        "Enabled": True,
        "Duration": 1,
        "Cutoff": 0,
        "Schedule": "cron(0 10 19 ? * * *)",
        "NextExecutionTime": next_execution_time,
    }
    maint_win: Any = EC2SSMMaintenanceWindows(
        hub_session=Session(),
        spoke_session=Session(),
        spoke_account_id="111111111111",
        table_name="maint-win-table",
        scheduler_interval=10,
        logger=MockLogger(),
    )
    account = "1111"
    region = "us-east-1"
    maint_win.process_ssm_window(window, ssm_windows_db, account, region)
    mock_store.return_value.put_window_dynamodb.assert_called_with(
        window=window, account=account, region=region
    )
