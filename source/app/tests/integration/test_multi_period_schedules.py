# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from datetime import datetime, timezone

from instance_scheduler.model.period_definition import PeriodDefinition
from instance_scheduler.schedulers.instance_states import InstanceStates
from tests.integration.helpers.ec2_helpers import get_current_state
from tests.integration.helpers.run_handler import multi_period_schedule
from tests.integration.helpers.schedule_helpers import quick_time


def test_adjacent_periods_do_not_get_stopped_in_the_middle(
    ec2_instance: str,
    ec2_instance_states: InstanceStates,
) -> None:
    with multi_period_schedule(
        period_definitions=[
            PeriodDefinition(name="period1", begintime="5:00", endtime="10:00"),
            PeriodDefinition(name="period2", begintime="10:01", endtime="15:00"),
        ]
    ) as context:
        # in period 1 (populates state table)
        context.run_scheduling_request_handler(dt=quick_time(9, 30))
        assert get_current_state(ec2_instance) == "running"

        # time between periods
        context.run_scheduling_request_handler(dt=quick_time(10, 0, 30))
        assert get_current_state(ec2_instance) == "running"


def test_adjacent_periods_across_midnight_do_not_get_stopped_in_the_middle(
    ec2_instance: str,
    ec2_instance_states: InstanceStates,
) -> None:

    with multi_period_schedule(
        period_definitions=[
            PeriodDefinition(name="period1", begintime="5:00", endtime="23:59"),
            PeriodDefinition(name="period2", begintime="0:00", endtime="3:00"),
        ]
    ) as context:
        # in period 1 (populates state table)
        context.run_scheduling_request_handler(dt=quick_time(23, 30))
        assert get_current_state(ec2_instance) == "running"

        # just before midnight
        context.run_scheduling_request_handler(dt=quick_time(23, 59, 59))
        assert get_current_state(ec2_instance) == "running"

        # midnight
        context.run_scheduling_request_handler(dt=quick_time(0, 0, 0))
        assert get_current_state(ec2_instance) == "running"


def test_not_running_period(
    ec2_instance: str,
    ec2_instance_states: InstanceStates,
) -> None:
    # example schedule that turns an instance off from 6pm to 7pm on tuesdays
    with multi_period_schedule(
        period_definitions=[
            PeriodDefinition(
                name="period1", begintime="0:00", endtime="18:00", weekdays={"1"}
            ),
            PeriodDefinition(
                name="period2", begintime="19:00", endtime="23:59", weekdays={"1"}
            ),
            PeriodDefinition(name="period3", weekdays={"2-0"}),
        ]
    ) as context:
        # initial run (populates state table
        context.run_scheduling_request_handler(
            dt=datetime(2024, 1, 2, 17, 55, tzinfo=timezone.utc)
        )
        assert get_current_state(instance_id=ec2_instance) == "running"

        # stop at 6pm on Tuesday
        context.run_scheduling_request_handler(
            dt=datetime(2024, 1, 2, 18, 0, tzinfo=timezone.utc)
        )
        assert get_current_state(instance_id=ec2_instance) == "stopped"

        # start again at 7pm
        context.run_scheduling_request_handler(
            dt=datetime(2024, 1, 2, 19, 0, tzinfo=timezone.utc)
        )
        assert get_current_state(instance_id=ec2_instance) == "running"

        # don't stop at 6pm on Wednesday
        context.run_scheduling_request_handler(
            dt=datetime(2024, 1, 3, 18, 0, tzinfo=timezone.utc)
        )
        assert get_current_state(instance_id=ec2_instance) == "running"
