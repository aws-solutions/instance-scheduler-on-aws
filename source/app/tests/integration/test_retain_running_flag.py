# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from instance_scheduler.schedulers.instance_states import InstanceStates
from tests.integration.helpers.ec2_helpers import get_current_state, start_ec2_instances
from tests.integration.helpers.run_handler import simple_schedule
from tests.integration.helpers.schedule_helpers import quick_time


def setup_retain_running_scenario(
    ec2_instance: str,
) -> None:
    """
    The retain_running flag comes into effect when an instance is manually started by
    a customer outside of normal schedule control

    this method simulates the initial prerequisites for a schedule to enter this scenario

    scenario simulated:
    - running period of 10-20,
    - instance was stopped under normal circumstances (last desired state = stopped),
    - customer started instance manually at some point during the last off period and is discovered as already
        running when the scheduler tries to start the instance at the beginning of the period (10)

    this should cause the instance to be identified as having been started manually and will tag it with
        the retain_running flag
    """
    with simple_schedule(
        begintime="10:00", endtime="20:00", retain_running=True
    ) as context:
        # stopped under normal conditions (populates state table)
        context.run_scheduling_request_handler(dt=quick_time(20, 0))
        assert get_current_state(ec2_instance) == "stopped"

        # customer manually starts instance
        start_ec2_instances(ec2_instance)

        # already running instance is identified when it should normally be started
        context.run_scheduling_request_handler(dt=quick_time(10, 0))


def test_instance_is_stopped_at_end_of_period_when_flag_is_not_set(
    ec2_instance: str,
    ec2_instance_states: InstanceStates,
) -> None:
    setup_retain_running_scenario(
        ec2_instance,
    )

    with simple_schedule(
        begintime="10:00", endtime="20:00", retain_running=False
    ) as context:
        context.run_scheduling_request_handler(quick_time(20, 0))
        assert get_current_state(ec2_instance) == "stopped"


def test_instance_is_not_stopped_at_end_of_period_when_flag_is_set(
    ec2_instance: str,
    ec2_instance_states: InstanceStates,
) -> None:
    setup_retain_running_scenario(
        ec2_instance,
    )

    with simple_schedule(
        begintime="10:00", endtime="20:00", retain_running=True
    ) as context:
        context.run_scheduling_request_handler(quick_time(20, 0))
        assert get_current_state(ec2_instance) == "running"


def test_retain_running_behavior_over_multiple_scheduling_cycles(
    ec2_instance: str,
    ec2_instance_states: InstanceStates,
) -> None:
    setup_retain_running_scenario(
        ec2_instance,
    )

    with simple_schedule(
        begintime="10:00", endtime="20:00", retain_running=True
    ) as context:
        # ----------------------------Period Start--------------------------#
        context.run_scheduling_request_handler(quick_time(10, 0))
        assert get_current_state(ec2_instance) == "running"

        # ----------------------------Period end--------------------------#
        context.run_scheduling_request_handler(quick_time(20, 0))
        assert get_current_state(ec2_instance) == "running"

        # ----------------------------Period Start--------------------------#
        context.run_scheduling_request_handler(quick_time(10, 0))
        assert get_current_state(ec2_instance) == "running"

        # ----------------------------Period end--------------------------#
        context.run_scheduling_request_handler(quick_time(20, 0))
        assert get_current_state(ec2_instance) == "running"

    # disable retain-running flag to confirm running behavior was actually because of the flag
    with simple_schedule(
        begintime="10:00", endtime="20:00", retain_running=False
    ) as context:
        # ----------------------------Period Start--------------------------#
        context.run_scheduling_request_handler(quick_time(10, 0))
        assert get_current_state(ec2_instance) == "running"

        # ----------------------------Period end--------------------------#
        context.run_scheduling_request_handler(quick_time(20, 0))
        assert get_current_state(ec2_instance) == "stopped"

        # ----------------------------Period Start--------------------------#
        context.run_scheduling_request_handler(quick_time(10, 0))
        assert get_current_state(ec2_instance) == "running"

        # ----------------------------Period end--------------------------#
        context.run_scheduling_request_handler(quick_time(20, 0))
        assert get_current_state(ec2_instance) == "stopped"
