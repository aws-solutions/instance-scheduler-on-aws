# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from freezegun import freeze_time
from instance_scheduler.configuration.scheduling_context import SchedulingContext
from tests.integration.helpers.ec2_helpers import get_current_state
from tests.integration.helpers.run_handler import (
    SchedulingTestContext,
    simple_schedule,
)
from tests.integration.helpers.schedule_helpers import quick_time
from tests.test_utils.mock_environs.mock_scheduling_request_environment import (
    MockSchedulingRequestEnvironment,
)

NOW = datetime(2026, 8, 31, 11, 42, 0, tzinfo=timezone.utc)
INTERVAL = timedelta(
    minutes=MockSchedulingRequestEnvironment().scheduling_interval_minutes
)


def _populate_running_state(context: SchedulingTestContext, ec2_instance: str) -> None:
    context.run_scheduling_request_handler(dt=quick_time(15, 0))
    assert get_current_state(ec2_instance) == "running"


@freeze_time(NOW)
def test_replayed_request_from_hours_ago_is_dropped(
    ec2_instance: str,
    scheduling_context: SchedulingContext,
) -> None:
    # reproduces a lambda async duplicate delivered ~6 hours after dispatch
    with simple_schedule(begintime="10:00", endtime="20:00") as context:
        _populate_running_state(context, ec2_instance)

        result = context.run_scheduling_request_handler(
            dt=quick_time(9, 0),
            dispatch_time=(NOW - timedelta(hours=5, minutes=47)).isoformat(),
        )

        assert json.loads(result)["skipped"] == "stale_request"
        assert get_current_state(ec2_instance) == "running"


@freeze_time(NOW)
def test_request_older_than_scheduling_interval_is_dropped(
    ec2_instance: str,
    scheduling_context: SchedulingContext,
) -> None:
    with simple_schedule(begintime="10:00", endtime="20:00") as context:
        _populate_running_state(context, ec2_instance)

        with patch(
            "instance_scheduler.handler.scheduling_request.logger.warning"
        ) as mock_warning:
            result = context.run_scheduling_request_handler(
                dt=quick_time(9, 0),
                dispatch_time=(NOW - INTERVAL - timedelta(seconds=1)).isoformat(),
            )

        assert json.loads(result)["skipped"] == "stale_request"
        assert get_current_state(ec2_instance) == "running"
        mock_warning.assert_called_once()
        assert mock_warning.call_args.args[0] == "Dropping stale scheduling request"
        assert mock_warning.call_args.kwargs["extra"]["age_seconds"] == (
            INTERVAL.total_seconds() + 1
        )


@freeze_time(NOW)
@pytest.mark.parametrize(
    "dispatch_time",
    [
        (NOW - INTERVAL).isoformat(),  # exactly one interval old
        (NOW - timedelta(seconds=5)).isoformat(),
        (NOW + timedelta(seconds=5)).isoformat(),  # clock skew
    ],
)
def test_request_within_scheduling_interval_is_processed(
    dispatch_time: str,
    ec2_instance: str,
    scheduling_context: SchedulingContext,
) -> None:
    with simple_schedule(begintime="10:00", endtime="20:00") as context:
        _populate_running_state(context, ec2_instance)

        context.run_scheduling_request_handler(
            dt=quick_time(20, 0), dispatch_time=dispatch_time
        )

        assert get_current_state(ec2_instance) == "stopped"
