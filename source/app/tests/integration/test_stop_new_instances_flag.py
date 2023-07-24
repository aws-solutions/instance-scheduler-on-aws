# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import datetime

import boto3
from mypy_boto3_ec2.client import EC2Client

from instance_scheduler.configuration.instance_schedule import InstanceSchedule
from instance_scheduler.configuration.running_period import RunningPeriod
from instance_scheduler.handler.scheduling_request import SchedulingRequestHandler
from instance_scheduler.schedulers.instance_states import InstanceStates
from tests.context import MockLambdaContext
from tests.integration.helpers.ec2_helpers import get_current_state
from tests.integration.helpers.schedule_helpers import quick_time
from tests.integration.helpers.scheduling_context_builder import (
    build_context,
    build_scheduling_event,
)


def test_new_instance_stops_when_outside_period_and_flag_is_set(
    ec2_instance: str, ec2_instance_states: InstanceStates
) -> None:
    """
    ----inputs----
    schedule:
        begintime = 10:00
        endtime = 20:00
    current time: 5:00
    instance: running
    last_desired_state: none (not seen before)

    ----expect----
    instance: stopped
    """
    # ----------------------------Event Definition--------------------------#
    context = build_context(
        current_dt=quick_time(5, 0, 0),
        schedules={
            "test-schedule": InstanceSchedule(
                name="test-schedule",
                stop_new_instances=True,
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
    # ----------------------------EC2 Instance-------------------------#
    ec2_client: EC2Client = boto3.client("ec2")
    ec2_client.start_instances(InstanceIds=[ec2_instance])

    # ------------------------Last Desired State------------------------#
    # none set (never been seen before)

    # -------------------run handler------------------------#
    handler = SchedulingRequestHandler(event, MockLambdaContext())
    handler.handle_request()

    # ---------------------validate result---------------------#
    assert get_current_state(ec2_instance) == "stopped"


def test_instance_does_not_stop_when_it_is_not_new(
    ec2_instance: str, ec2_instance_states: InstanceStates
) -> None:
    """
    the stop new instances flag should only affect instances that are "new" to the scheduler
    ----inputs----
    schedule:
        begintime = 10:00
        endtime = 20:00
    current time: 5:00
    instance: running
    last_desired_state: stopped (normal expected from being outside a period)

    ----expect----
    instance: running
    """
    # ----------------------------Event Definition--------------------------#
    context = build_context(
        current_dt=quick_time(5, 0, 0),
        schedules={
            "test-schedule": InstanceSchedule(
                name="test-schedule",
                stop_new_instances=True,
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
    # ----------------------------EC2 Instance-------------------------#
    ec2_client: EC2Client = boto3.client("ec2")
    ec2_client.start_instances(InstanceIds=[ec2_instance])

    # ------------------------Last Desired State------------------------#
    ec2_instance_states.set_instance_state(ec2_instance, "stopped")
    ec2_instance_states.save()

    # -------------------run handler------------------------#
    handler = SchedulingRequestHandler(event, MockLambdaContext())
    handler.handle_request()

    # ---------------------validate result---------------------#
    assert get_current_state(ec2_instance) == "running"


def test_new_instance_does_not_stop_when_outside_period_and_flag_is_not_set(
    ec2_instance: str, ec2_instance_states: InstanceStates
) -> None:
    """
    ----inputs----
    schedule:
        begintime = 10:00
        endtime = 20:00
    current time: 5:00
    instance: running
    last_desired_state: none (not seen before)

    ----expect----
    instance: stopped
    """
    # ----------------------------Event Definition--------------------------#
    context = build_context(
        current_dt=quick_time(5, 0, 0),
        schedules={
            "test-schedule": InstanceSchedule(
                name="test-schedule",
                stop_new_instances=False,
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
    # ----------------------------EC2 Instance-------------------------#
    ec2_client: EC2Client = boto3.client("ec2")
    ec2_client.start_instances(InstanceIds=[ec2_instance])

    # ------------------------Last Desired State------------------------#
    # none set (never been seen before)

    # -------------------run handler------------------------#
    handler = SchedulingRequestHandler(event, MockLambdaContext())
    handler.handle_request()

    # ---------------------validate result---------------------#
    assert get_current_state(ec2_instance) == "running"


def test_new_instance_does_not_stop_when_inside_period_and_flag_is_set(
    ec2_instance: str, ec2_instance_states: InstanceStates
) -> None:
    """
    flag should only stop instances that are newly detected when outside a valid running period
    ----inputs----
    schedule:
        begintime = 10:00
        endtime = 20:00
    current time: 15:00
    instance: running
    last_desired_state: none (not seen before)

    ----expect----
    instance: running
    """
    # ----------------------------Event Definition--------------------------#
    context = build_context(
        current_dt=quick_time(15, 0, 0),
        schedules={
            "test-schedule": InstanceSchedule(
                name="test-schedule",
                stop_new_instances=True,
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
    # ----------------------------EC2 Instance-------------------------#
    ec2_client: EC2Client = boto3.client("ec2")
    ec2_client.start_instances(InstanceIds=[ec2_instance])

    # ------------------------Last Desired State------------------------#
    # none set (never been seen before)

    # -------------------run handler------------------------#
    handler = SchedulingRequestHandler(event, MockLambdaContext())
    handler.handle_request()

    # ---------------------validate result---------------------#
    assert get_current_state(ec2_instance) == "running"
