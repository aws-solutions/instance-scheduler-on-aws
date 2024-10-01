# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from datetime import datetime

import pytest
from dateutil.tz import tzutc

from instance_scheduler.schedulers.instance_states import InstanceStates
from tests.integration.helpers.ec2_helpers import get_current_state
from tests.integration.helpers.run_handler import simple_schedule

# using september 2024 which starts on a Sunday
# 01 02 03 04 05 06 07
# 08 09 10 11 12 13 14
# 15 16 17 18 19 20 21
# 22 23 24 25 26 27 28
# 29 30 01


@pytest.mark.skip(
    "long-running test (about 60second by itself) so skipping by default. "
    "this can be run manually as an e2e test over this behavior while the individual "
    "pieces also have more fine grained unit tests elsewhere"
)
@pytest.mark.parametrize(
    "weekdayExpr, dayRunning",
    [
        ("Sun#1", 1),
        ("Mon#1", 2),
        ("Mon#3", 16),
        ("Fri#4", 27),
        ("Tue#5", 30),
    ],
)
def test_nth_weekday_scheduling(
    weekdayExpr: str,
    dayRunning: int,
    ec2_instance: str,
    ec2_instance_states: InstanceStates,
) -> None:

    with simple_schedule(weekdays={weekdayExpr}) as context:
        for day in range(1, 30):
            context.run_scheduling_request_handler(
                datetime(2024, 9, day, 12, tzinfo=tzutc())
            )
            assert (
                get_current_state(ec2_instance) == "running"
                if day == dayRunning
                else "stopped"
            ), f"{get_current_state(ec2_instance)} on {day} when should be {'running' if day == dayRunning else 'stopped'}"
