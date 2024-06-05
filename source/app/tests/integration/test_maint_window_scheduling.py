# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from datetime import datetime, timezone
from typing import Sequence
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

from instance_scheduler.maint_win.ssm_mw_client import SSMMWClient
from instance_scheduler.model import (
    EC2SSMMaintenanceWindow,
    EC2SSMMaintenanceWindowStore,
    MWStore,
)
from instance_scheduler.schedulers.instance_states import InstanceStates
from tests.integration.helpers.ec2_helpers import get_current_state, stop_ec2_instances
from tests.integration.helpers.run_handler import simple_schedule
from tests.test_utils.mock_scheduling_request_environment import (
    MockSchedulingRequestEnvironment,
)


def invoke_scheduling_request_handler_with_maintenance_windows(
    ssm_maintenance_windows: Sequence[str],
) -> None:
    with simple_schedule(
        begintime="20:00",
        endtime="22:00",
        ssm_maintenance_window=ssm_maintenance_windows,
    ) as context:
        context.run_scheduling_request_handler(
            dt=datetime(year=2024, month=1, day=25, hour=14, tzinfo=timezone.utc),
            environment=MockSchedulingRequestEnvironment(
                enable_ec2_ssm_maintenance_windows=True
            ),
        )


def test_maint_window_is_enforced(
    ec2_instance: str,
    ec2_instance_states: InstanceStates,
    maint_win_store: EC2SSMMaintenanceWindowStore,
) -> None:
    # maintenance window is active (exists in maint window table)
    # instance should start because window is enforced

    maint_win_store.put_window_dynamodb(
        EC2SSMMaintenanceWindow(
            account_id="123456789012",
            region="us-east-1",
            window_id="mw-00000000000000000",
            window_name="my-active-window",
            schedule_timezone=ZoneInfo("UTC"),
            next_execution_time=datetime(
                year=2024, month=1, day=25, hour=14, tzinfo=timezone.utc
            ),
            duration_hours=1,
        )
    )

    with simple_schedule(
        begintime="20:00",
        endtime="22:00",
        ssm_maintenance_window=["my-active-window"],
    ) as context:
        # start with instance stopped
        stop_ec2_instances(ec2_instance)
        assert get_current_state(ec2_instance) == "stopped"

        context.run_scheduling_request_handler(
            dt=datetime(year=2024, month=1, day=25, hour=14, tzinfo=timezone.utc),
            environment=MockSchedulingRequestEnvironment(
                enable_ec2_ssm_maintenance_windows=True
            ),
        )

    assert get_current_state(ec2_instance) == "running"


def test_inactive_maintenance_windows_have_no_effect(
    ec2_instance: str,
    ec2_instance_states: InstanceStates,
    mw_store: MWStore,
) -> None:
    # multiple maintenance windows (none are active)
    # instance should stay stopped since no maintenance windows are active
    with simple_schedule(
        begintime="20:00",
        endtime="22:00",
        ssm_maintenance_window=["my-inactive-window"],
    ) as context:
        # start with instance stopped
        stop_ec2_instances(ec2_instance)
        assert get_current_state(ec2_instance) == "stopped"

        context.run_scheduling_request_handler(
            dt=datetime(year=2024, month=1, day=25, hour=14, tzinfo=timezone.utc),
            environment=MockSchedulingRequestEnvironment(
                enable_ec2_ssm_maintenance_windows=True
            ),
        )

    assert get_current_state(ec2_instance) == "stopped"


@pytest.mark.parametrize(
    "active_window_name",
    [
        "my-window-a",
        "my-window-b",
    ],
)
def test_multiple_maintenance_windows_one_active(
    active_window_name: str,
    ec2_instance: str,
    ec2_instance_states: InstanceStates,
    maint_win_store: EC2SSMMaintenanceWindowStore,
) -> None:
    # maintenance window is active (exists in maint window table)
    # instance should start if any maintenance window is active

    maint_win_store.put_window_dynamodb(
        EC2SSMMaintenanceWindow(
            account_id="123456789012",
            region="us-east-1",
            window_id="mw-00000000000000000",
            window_name=active_window_name,
            schedule_timezone=ZoneInfo("UTC"),
            next_execution_time=datetime(
                year=2024, month=1, day=25, hour=14, tzinfo=timezone.utc
            ),
            duration_hours=1,
        )
    )

    with simple_schedule(
        begintime="20:00",
        endtime="22:00",
        ssm_maintenance_window=[
            "my-window-a",
            "my-window-b",
        ],
    ) as context:
        # start with instance stopped
        stop_ec2_instances(ec2_instance)
        assert get_current_state(ec2_instance) == "stopped"

        context.run_scheduling_request_handler(
            dt=datetime(year=2024, month=1, day=25, hour=14, tzinfo=timezone.utc),
            environment=MockSchedulingRequestEnvironment(
                enable_ec2_ssm_maintenance_windows=True
            ),
        )

    assert get_current_state(ec2_instance) == "running"


def test_all_maintenance_windows_sharing_non_unique_names_are_used(
    ec2_instance: str,
    ec2_instance_states: InstanceStates,
    mw_store: MWStore,
) -> None:
    non_unique_window_name = "non-unique-window-name"
    # windows share a name but have unique id
    # both should be used when the shared name is provided to the schedule
    windows = [
        EC2SSMMaintenanceWindow(
            account_id="123456789012",
            region="us-east-1",
            window_id="mw-00000000000000000",
            window_name=non_unique_window_name,
            schedule_timezone=ZoneInfo("UTC"),
            next_execution_time=datetime(
                year=2024, month=1, day=25, hour=14, tzinfo=timezone.utc
            ),
            duration_hours=1,
        ),
        EC2SSMMaintenanceWindow(
            account_id="123456789012",
            region="us-east-1",
            window_id="mw-00000000000000001",
            window_name=non_unique_window_name,
            schedule_timezone=ZoneInfo("UTC"),
            next_execution_time=datetime(
                year=2024, month=1, day=25, hour=18, tzinfo=timezone.utc
            ),
            duration_hours=1,
        ),
    ]

    with (
        simple_schedule(
            begintime="20:00",
            endtime="22:00",
            ssm_maintenance_window=[non_unique_window_name],  # only one name provided
        ) as context,
        patch.object(SSMMWClient, "get_mws_from_ssm", return_value=windows),
    ):
        # start with instance stopped
        stop_ec2_instances(ec2_instance)
        assert get_current_state(ec2_instance) == "stopped"

        # running during first maintenance window
        context.run_scheduling_request_handler(
            dt=datetime(year=2024, month=1, day=25, hour=14, tzinfo=timezone.utc),
            environment=MockSchedulingRequestEnvironment(
                enable_ec2_ssm_maintenance_windows=True,
            ),
        )
        assert get_current_state(ec2_instance) == "running"

        # stopped in between windows
        context.run_scheduling_request_handler(
            dt=datetime(year=2024, month=1, day=25, hour=16, tzinfo=timezone.utc),
            environment=MockSchedulingRequestEnvironment(
                enable_ec2_ssm_maintenance_windows=True
            ),
        )
        assert get_current_state(ec2_instance) == "stopped"

        # running during second maintenance window
        context.run_scheduling_request_handler(
            dt=datetime(year=2024, month=1, day=25, hour=18, tzinfo=timezone.utc),
            environment=MockSchedulingRequestEnvironment(
                enable_ec2_ssm_maintenance_windows=True
            ),
        )
        assert get_current_state(ec2_instance) == "running"
