# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Final
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

from boto3 import client
from boto3.session import Session
from botocore.stub import Stubber
from freezegun import freeze_time

from instance_scheduler.configuration.instance_schedule import InstanceSchedule
from instance_scheduler.cron.cron_recurrence_expression import CronRecurrenceExpression
from instance_scheduler.cron.expression import CronSingleValueNumeric
from instance_scheduler.model.maint_win import EC2SSMMaintenanceWindow

if TYPE_CHECKING:
    from mypy_boto3_ssm.client import SSMClient
    from mypy_boto3_ssm.type_defs import MaintenanceWindowIdentityTypeDef
else:
    SSMClient = object
    MaintenanceWindowIdentityTypeDef = object


# use common UTC zoneinfo in these tests to allow proper emulation of SSM API
utc_timezone: Final = ZoneInfo("Etc/UTC")


def to_identity(window: EC2SSMMaintenanceWindow) -> MaintenanceWindowIdentityTypeDef:
    if window.schedule_timezone == utc_timezone:
        next_execution_time = window.next_execution_time.strftime("%Y-%m-%dT%H:%M:%SZ")
    else:
        next_execution_time = window.next_execution_time.isoformat()

    return {
        "WindowId": window.window_id,
        "Duration": window.duration_hours,
        "Enabled": True,
        "Name": window.window_name,
        "NextExecutionTime": next_execution_time,
        "ScheduleTimezone": str(window.schedule_timezone),
    }


def assert_valid_maintenance_window_schedule(schedule: InstanceSchedule) -> None:
    """schedules generated from maintenance windows must have these properties"""
    assert schedule.override_status is None
    assert schedule.stop_new_instances is True
    assert schedule.ssm_maintenance_window is None
    assert schedule.enforced is True
    assert schedule.hibernate is False
    assert schedule.retain_running is False
    assert schedule.configured_in_stack is None

    for period in schedule.periods:
        assert period.get("instancetype") is None


scheduler_interval_minutes: Final = 5
expected_window_buffer: Final = 10 + scheduler_interval_minutes


def assert_schedule_matches_window(
    schedule: InstanceSchedule, window: EC2SSMMaintenanceWindow
) -> None:
    assert_valid_maintenance_window_schedule(schedule)

    assert schedule.timezone == window.schedule_timezone

    # does not handle multi-period windows
    assert len(schedule.periods) == 1
    period: Final = schedule.periods[0]["period"]

    # does not handle windows that cross day boundaries
    expected_begintime: Final = window.next_execution_time - timedelta(
        minutes=expected_window_buffer
    )
    assert period.begintime == expected_begintime.time()

    # does not handle windows that cross day boundaries
    expected_endtime: Final = window.next_execution_time + timedelta(
        hours=window.duration_hours
    )
    assert period.endtime == expected_endtime.time()

    assert period.cron_recurrence == CronRecurrenceExpression(
        months=CronSingleValueNumeric(value=window.next_execution_time.month),
        monthdays=CronSingleValueNumeric(value=window.next_execution_time.day),
    )


@contextmanager
def mock_ssm_windows(windows: Iterable[EC2SSMMaintenanceWindow]) -> Iterator[Session]:
    session: Final = Session()
    ssm: Final[SSMClient] = client("ssm")
    stub_ssm: Final = Stubber(ssm)
    setattr(session, "client", MagicMock(return_value=ssm))

    stub_ssm.add_response(
        "describe_maintenance_windows",
        {
            "WindowIdentities": list(map(to_identity, windows)),
        },
        {
            "Filters": [{"Key": "Enabled", "Values": ["true"]}],
        },
    )

    with stub_ssm:
        yield session


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
