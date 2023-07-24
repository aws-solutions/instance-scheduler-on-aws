# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import datetime

import boto3
from mypy_boto3_ec2.client import EC2Client

from instance_scheduler.configuration.running_period import RunningPeriod
from instance_scheduler.configuration.running_period_dict_element import (
    RunningPeriodDictElement,
)
from instance_scheduler.handler.scheduling_request import SchedulingRequestHandler
from instance_scheduler.schedulers.instance_states import InstanceStates
from tests.context import MockLambdaContext
from tests.integration.helpers.ec2_helpers import get_current_state
from tests.integration.helpers.schedule_helpers import quick_time
from tests.integration.helpers.scheduling_context_builder import (
    build_context,
    build_scheduling_event,
    custom_schedule,
)

one_sided_start = RunningPeriodDictElement(
    period=RunningPeriod(name="one-sided-start", begintime=datetime.time(10, 0, 0))
)

one_sided_stop = RunningPeriodDictElement(
    period=RunningPeriod(name="one-sided-stop", endtime=datetime.time(20, 0, 0))
)


def test_enforced_1_sided_start_does_not_stop_instances_before_start_time(
    ec2_instance: str, ec2_instance_states: InstanceStates
) -> None:
    # ----------------------------Event Definition--------------------------#
    context = build_context(
        current_dt=quick_time(5, 0, 0),
        schedules=custom_schedule(periods=[one_sided_start], enforced=True),
    )
    event = build_scheduling_event(context)
    # ----------------------------EC2 Instance-------------------------#
    ec2_client: EC2Client = boto3.client("ec2")
    ec2_client.start_instances(InstanceIds=[ec2_instance])

    # ------------------------Last Desired State------------------------#
    ec2_instance_states.set_instance_state(ec2_instance, "any")
    ec2_instance_states.save()

    # -------------------run handler------------------------#
    handler = SchedulingRequestHandler(event, MockLambdaContext())
    handler.handle_request()

    # ---------------------validate result---------------------#
    assert get_current_state(ec2_instance) == "running"


def test_enforced_1_sided_stop_does_not_start_instances_before_stop_time(
    ec2_instance: str, ec2_instance_states: InstanceStates
) -> None:
    # ----------------------------Event Definition--------------------------#
    context = build_context(
        current_dt=quick_time(5, 0, 0),
        schedules=custom_schedule(periods=[one_sided_stop], enforced=True),
    )
    event = build_scheduling_event(context)
    # ----------------------------EC2 Instance-------------------------#
    ec2_client: EC2Client = boto3.client("ec2")
    ec2_client.stop_instances(InstanceIds=[ec2_instance])

    # ------------------------Last Desired State------------------------#
    ec2_instance_states.set_instance_state(ec2_instance, "any")
    ec2_instance_states.save()

    # -------------------run handler------------------------#
    handler = SchedulingRequestHandler(event, MockLambdaContext())
    handler.handle_request()

    # ---------------------validate result---------------------#
    assert get_current_state(ec2_instance) == "stopped"


def test_1_sided_stop_stops_at_stop_time(
    ec2_instance: str, ec2_instance_states: InstanceStates
) -> None:
    # ----------------------------Event Definition--------------------------#
    context = build_context(
        current_dt=quick_time(20, 0, 0),
        schedules=custom_schedule(periods=[one_sided_stop]),
    )
    event = build_scheduling_event(context)
    # ----------------------------EC2 Instance-------------------------#
    ec2_client: EC2Client = boto3.client("ec2")
    ec2_client.start_instances(InstanceIds=[ec2_instance])

    # ------------------------Last Desired State------------------------#
    ec2_instance_states.set_instance_state(ec2_instance, "any")
    ec2_instance_states.save()

    # -------------------run handler------------------------#
    handler = SchedulingRequestHandler(event, MockLambdaContext())
    handler.handle_request()

    # ---------------------validate result---------------------#
    assert get_current_state(ec2_instance) == "stopped"


def test_1_sided_start_starts_at_start_time(
    ec2_instance: str, ec2_instance_states: InstanceStates
) -> None:
    # ----------------------------Event Definition--------------------------#
    context = build_context(
        current_dt=quick_time(10, 0, 0),
        schedules=custom_schedule(periods=[one_sided_start]),
    )
    event = build_scheduling_event(context)
    # ----------------------------EC2 Instance-------------------------#
    ec2_client: EC2Client = boto3.client("ec2")
    ec2_client.stop_instances(InstanceIds=[ec2_instance])

    # ------------------------Last Desired State------------------------#
    ec2_instance_states.set_instance_state(ec2_instance, "any")
    ec2_instance_states.save()

    # -------------------run handler------------------------#
    handler = SchedulingRequestHandler(event, MockLambdaContext())
    handler.handle_request()

    # ---------------------validate result---------------------#
    assert get_current_state(ec2_instance) == "running"
