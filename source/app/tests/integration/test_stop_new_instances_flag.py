# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from instance_scheduler.configuration.scheduling_context import SchedulingContext
from tests.integration.helpers.ec2_helpers import get_current_state, start_ec2_instances
from tests.integration.helpers.run_handler import simple_schedule
from tests.integration.helpers.schedule_helpers import quick_time


def test_new_instance_stops_when_outside_period_and_flag_is_set(
    ec2_instance: str,
    scheduling_context: SchedulingContext,
) -> None:
    with simple_schedule(
        begintime="10:00", endtime="20:00", stop_new_instances=True
    ) as context:
        assert get_current_state(ec2_instance) == "running"
        context.run_scheduling_request_handler(dt=quick_time(5, 0))
        assert get_current_state(ec2_instance) == "stopped"


def test_instance_does_not_stop_when_it_is_not_new(
    ec2_instance: str,
    scheduling_context: SchedulingContext,
) -> None:
    with simple_schedule(
        begintime="10:00", endtime="20:00", stop_new_instances=True
    ) as context:
        # load instance into registry
        context.run_scheduling_request_handler(dt=quick_time(5, 0))

        start_ec2_instances(ec2_instance)

        context.run_scheduling_request_handler(dt=quick_time(5, 0))
        assert get_current_state(ec2_instance) == "running"


def test_new_instance_does_not_stop_when_outside_period_and_flag_is_not_set(
    ec2_instance: str,
    scheduling_context: SchedulingContext,
) -> None:
    with simple_schedule(
        begintime="10:00", endtime="20:00", stop_new_instances=False
    ) as context:
        assert get_current_state(ec2_instance) == "running"
        context.run_scheduling_request_handler(dt=quick_time(5, 0))
        assert get_current_state(ec2_instance) == "running"


def test_new_instance_does_not_stop_when_inside_period_and_flag_is_set(
    ec2_instance: str,
    scheduling_context: SchedulingContext,
) -> None:
    with simple_schedule(
        begintime="10:00", endtime="20:00", stop_new_instances=True
    ) as context:
        assert get_current_state(ec2_instance) == "running"
        context.run_scheduling_request_handler(dt=quick_time(15, 0))
        assert get_current_state(ec2_instance) == "running"
