# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import datetime
from typing import Any

import boto3
from mypy_boto3_ec2.client import EC2Client

from instance_scheduler.configuration.instance_schedule import InstanceSchedule
from instance_scheduler.configuration.running_period import RunningPeriod
from instance_scheduler.handler.scheduling_request import SchedulingRequestHandler
from instance_scheduler.schedulers.instance_states import InstanceStates
from tests.context import MockLambdaContext
from tests.integration.helpers.ec2_helpers import get_current_state
from tests.integration.helpers.schedule_helpers import at_time
from tests.integration.helpers.scheduling_context_builder import (
    build_context,
    build_scheduling_event,
)


def schedule_event_at_time(
    time: datetime.time, retain_running_flag: bool = True
) -> Any:
    """
    helper method for quickly building a scheduling event with the following:
    begintime: 10:00
    endtime: 20:00
    retain_running: true
    """
    context = build_context(
        current_dt=at_time(time),
        schedules={
            "test-schedule": InstanceSchedule(
                name="test-schedule",
                retain_running=retain_running_flag,
                periods=[
                    {
                        "period": RunningPeriod(
                            name="test-period",
                            begintime=datetime.time(10, 0, 0),
                            endtime=datetime.time(20, 0, 0),
                        )
                    }
                ],
            )
        },
    )

    event = build_scheduling_event(context)

    return event


def setup_retain_running_scenario(
    ec2_instance: str,
    ec2_instance_states: InstanceStates,
    retain_running_flag: bool = True,
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
    # ----------------------------Event Definition--------------------------#
    event = schedule_event_at_time(
        datetime.time(10, 0, 0), retain_running_flag=retain_running_flag
    )
    # ----------------------------EC2 Instance-------------------------#
    ec2_client: EC2Client = boto3.client("ec2")
    ec2_client.start_instances(InstanceIds=[ec2_instance])

    # ------------------------Last Desired State------------------------#
    ec2_instance_states.set_instance_state(ec2_instance, "stopped")
    ec2_instance_states.save()

    # -------------------run handler------------------------#
    handler = SchedulingRequestHandler(event, MockLambdaContext())
    handler.handle_request()


def test_instance_is_stopped_at_end_of_period_when_flag_is_not_set(
    ec2_instance: str, ec2_instance_states: InstanceStates
) -> None:
    # ----------------------------Setup--------------------------#
    setup_retain_running_scenario(
        ec2_instance, ec2_instance_states, retain_running_flag=False
    )

    # Ec2 instance and instance states should already be setup now

    # ----------------------------Event Definition--------------------------#
    event = schedule_event_at_time(datetime.time(20, 0, 0), retain_running_flag=False)

    # -------------------run handler------------------------#
    handler = SchedulingRequestHandler(event, MockLambdaContext())
    handler.handle_request()

    # ---------------------validate result---------------------#
    assert get_current_state(ec2_instance) == "stopped"


def test_instance_is_not_stopped_at_end_of_period_when_flag_is_set(
    ec2_instance: str, ec2_instance_states: InstanceStates
) -> None:
    # ----------------------------Setup--------------------------#
    setup_retain_running_scenario(
        ec2_instance, ec2_instance_states, retain_running_flag=True
    )

    # Ec2 instance and instance states should already be setup now

    # ----------------------------Event Definition--------------------------#
    event = schedule_event_at_time(datetime.time(20, 0, 0))

    # -------------------run handler------------------------#
    handler = SchedulingRequestHandler(event, MockLambdaContext())
    handler.handle_request()

    # ---------------------validate result---------------------#
    assert get_current_state(ec2_instance) == "running"


def test_retain_running_behavior_over_multiple_scheduling_cycles(
    ec2_instance: str, ec2_instance_states: InstanceStates
) -> None:
    # ----------------------------Setup--------------------------#
    setup_retain_running_scenario(
        ec2_instance, ec2_instance_states, retain_running_flag=True
    )

    for i in range(1, 3):
        # ----------------------------Period Start--------------------------#
        event = schedule_event_at_time(datetime.time(10, 0, 0))
        handler = SchedulingRequestHandler(event, MockLambdaContext())
        handler.handle_request()

        assert get_current_state(ec2_instance) == "running"

        # ----------------------------Period End----------------------------#
        event = schedule_event_at_time(datetime.time(20, 0, 0))
        handler = SchedulingRequestHandler(event, MockLambdaContext())
        handler.handle_request()

        assert get_current_state(ec2_instance) == "running"

    # disable retain-running flag to confirm running behavior was actually because of the flag
    # ----------------------------Period Start--------------------------#
    event = schedule_event_at_time(datetime.time(10, 0, 0), retain_running_flag=False)
    handler = SchedulingRequestHandler(event, MockLambdaContext())
    handler.handle_request()

    assert get_current_state(ec2_instance) == "running"

    # ----------------------------Period End----------------------------#
    event = schedule_event_at_time(datetime.time(20, 0, 0), retain_running_flag=False)
    handler = SchedulingRequestHandler(event, MockLambdaContext())
    handler.handle_request()

    assert get_current_state(ec2_instance) == "stopped"
