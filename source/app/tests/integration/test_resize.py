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


def test_stopped_instance_resized(
    ec2_instance: str, ec2_instance_states: InstanceStates
) -> None:
    ec2_client: EC2Client = boto3.client("ec2")
    ec2_client.stop_instances(InstanceIds=[ec2_instance])
    ec2_client.modify_instance_attribute(
        InstanceId=ec2_instance, InstanceType={"Value": "c6g.medium"}
    )

    desired_instance_type = "c6g.2xlarge"

    context = build_context(
        current_dt=quick_time(10, 0, 0),
        schedules={
            "test-schedule": InstanceSchedule(
                name="test-schedule",
                periods=[
                    {
                        "period": RunningPeriod(
                            name="test-period",
                            begintime=datetime.time(10, 0, 0),
                            endtime=datetime.time(20, 0, 0),
                        ),
                        "instancetype": desired_instance_type,
                    }
                ],
            )
        },
    )

    event = build_scheduling_event(context)

    ec2_instance_states.set_instance_state(ec2_instance, "stopped")
    ec2_instance_states.save()

    handler = SchedulingRequestHandler(event, MockLambdaContext())
    handler.handle_request()

    assert get_current_state(ec2_instance) == "running"
    assert (
        ec2_client.describe_instances(InstanceIds=[ec2_instance])["Reservations"][0][
            "Instances"
        ][0]["InstanceType"]
        == desired_instance_type
    )


def test_running_instance_is_stopped_for_resize(
    ec2_instance: str, ec2_instance_states: InstanceStates
) -> None:
    ec2_client: EC2Client = boto3.client("ec2")
    ec2_client.stop_instances(InstanceIds=[ec2_instance])
    ec2_client.modify_instance_attribute(
        InstanceId=ec2_instance, InstanceType={"Value": "c6g.medium"}
    )
    ec2_client.start_instances(InstanceIds=[ec2_instance])

    desired_instance_type = "c6g.2xlarge"

    context = build_context(
        current_dt=quick_time(15, 0, 0),
        schedules={
            "test-schedule": InstanceSchedule(
                name="test-schedule",
                periods=[
                    {
                        "period": RunningPeriod(
                            name="test-period",
                            begintime=datetime.time(10, 0, 0),
                            endtime=datetime.time(20, 0, 0),
                        ),
                        "instancetype": desired_instance_type,
                    }
                ],
            )
        },
    )

    event = build_scheduling_event(context)

    ec2_instance_states.set_instance_state(ec2_instance, "running")
    ec2_instance_states.save()

    handler = SchedulingRequestHandler(event, MockLambdaContext())
    handler.handle_request()

    ec2_instance_states.load(account="123456789012", region="us-east-1")
    assert get_current_state(ec2_instance) == "stopped"

    # rerun handler to confirm the resize would be finished next interval

    handler.handle_request()
    assert get_current_state(ec2_instance) == "running"
    assert (
        ec2_client.describe_instances(InstanceIds=[ec2_instance])["Reservations"][0][
            "Instances"
        ][0]["InstanceType"]
        == desired_instance_type
    )
