# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from instance_scheduler.schedulers.instance_states import InstanceStates
from tests.integration.helpers.ec2_helpers import (
    get_current_state,
    start_ec2_instances,
    stop_ec2_instances,
)
from tests.integration.helpers.run_handler import simple_schedule
from tests.integration.helpers.schedule_helpers import quick_time


def test_ec2_starts_at_beginning_of_period(
    ec2_instance: str,
    ec2_instance_states: InstanceStates,
) -> None:
    # instance is already stopped
    stop_ec2_instances(ec2_instance)
    with simple_schedule(begintime="10:00", endtime="20:00") as context:
        # before start of period (populates state table)
        context.run_scheduling_request_handler(dt=quick_time(9, 55))
        assert get_current_state(ec2_instance) == "stopped"
        # start of period
        context.run_scheduling_request_handler(dt=quick_time(10, 0))
        assert get_current_state(ec2_instance) == "running"


def test_ec2_stops_at_end_of_period(
    ec2_instance: str,
    ec2_instance_states: InstanceStates,
) -> None:
    with simple_schedule(begintime="10:00", endtime="20:00") as context:
        # run before end of period (populates state table)
        context.run_scheduling_request_handler(dt=quick_time(19, 55, 0))
        assert get_current_state(ec2_instance) == "running"
        # run at end of period
        context.run_scheduling_request_handler(dt=quick_time(20, 0, 0))
        assert get_current_state(ec2_instance) == "stopped"


def test_instance_is_not_restarted_if_stopped_during_running_period(
    ec2_instance: str,
    ec2_instance_states: InstanceStates,
) -> None:
    # instance running in period
    with simple_schedule(begintime="10:00", endtime="20:00") as context:
        context.run_scheduling_request_handler(dt=quick_time(15, 0, 0))
        assert get_current_state(ec2_instance) == "running"

        # cx stops instance manually
        stop_ec2_instances(ec2_instance)

        # instance is not restarted
        context.run_scheduling_request_handler(dt=quick_time(15, 5, 0))
        assert get_current_state(ec2_instance) == "stopped"


def test_instance_is_restarted_if_schedule_is_enforced(
    ec2_instance: str,
    ec2_instance_states: InstanceStates,
) -> None:
    with simple_schedule(begintime="10:00", endtime="20:00", enforced=True) as context:
        # instance running in period
        context.run_scheduling_request_handler(dt=quick_time(15, 0, 0))
        assert get_current_state(ec2_instance) == "running"

        # cx stops instance manually
        stop_ec2_instances(ec2_instance)

        # instance is restarted
        context.run_scheduling_request_handler(dt=quick_time(15, 5, 0))
        assert get_current_state(ec2_instance) == "running"


def test_instance_is_not_stopped_if_started_outside_running_period(
    ec2_instance: str,
    ec2_instance_states: InstanceStates,
) -> None:
    stop_ec2_instances(ec2_instance)

    with simple_schedule(begintime="10:00", endtime="20:00") as context:
        # instance stopped outside period
        context.run_scheduling_request_handler(dt=quick_time(22, 0, 0))
        assert get_current_state(ec2_instance) == "stopped"

        # cx starts instance manually
        start_ec2_instances(ec2_instance)

        # instance is not stopped
        context.run_scheduling_request_handler(dt=quick_time(22, 5, 0))
        assert get_current_state(ec2_instance) == "running"


def test_instance_is_stopped_if_started_outside_running_period_when_schedule_is_enforced(
    ec2_instance: str,
    ec2_instance_states: InstanceStates,
) -> None:
    stop_ec2_instances(ec2_instance)

    with simple_schedule(begintime="10:00", endtime="20:00", enforced=True) as context:
        # instance stopped outside period
        context.run_scheduling_request_handler(dt=quick_time(22, 0, 0))
        assert get_current_state(ec2_instance) == "stopped"

        # cx starts instance manually
        start_ec2_instances(ec2_instance)

        # instance is not stopped
        context.run_scheduling_request_handler(dt=quick_time(22, 5, 0))
        assert get_current_state(ec2_instance) == "stopped"
