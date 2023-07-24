# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from datetime import datetime, time, timezone

import boto3
import pytest
from mypy_boto3_ec2.client import EC2Client

from instance_scheduler.configuration.instance_schedule import InstanceSchedule
from instance_scheduler.configuration.running_period import RunningPeriod
from instance_scheduler.configuration.running_period_dict_element import (
    RunningPeriodDictElement,
)
from instance_scheduler.handler.scheduling_request import SchedulingRequestHandler
from instance_scheduler.schedulers.instance_states import InstanceStates
from tests.context import MockLambdaContext
from tests.integration.helpers.ec2_helpers import get_current_state
from tests.integration.helpers.scheduling_context_builder import (
    build_context,
    build_scheduling_event,
)

stop_after_noon_period: RunningPeriodDictElement = {
    "period": RunningPeriod(
        name="test-period",
        begintime=time(0, 0, 0),
        endtime=time(12, 0, 0),
    )
}


def tz_instance(tz_name: str) -> tuple[InstanceSchedule, str]:
    ec2_client: EC2Client = boto3.client("ec2")
    instance_id = new_ec2_instance(ec2_client)
    ec2_client.create_tags(
        Resources=[instance_id], Tags=[{"Key": "Schedule", "Value": tz_name}]
    )

    schedule = InstanceSchedule(
        name=tz_name,
        timezone=tz_name,
        periods=[stop_after_noon_period],
        enforced=True,
        stop_new_instances=True,
    )

    return schedule, instance_id


def new_ec2_instance(ec2_client: EC2Client) -> str:
    ami = "ami-0889ff9188674a22a"
    instance_id: str = ec2_client.run_instances(ImageId=ami, MinCount=1, MaxCount=1)[
        "Instances"
    ][0]["InstanceId"]
    return instance_id


def test_passing_tz_unaware_dt_to_scheduling_request_handler_throws_error() -> None:
    context = build_context(current_dt=datetime(2023, 6, 19, 12, 0, 0))
    event = build_scheduling_event(context)

    with pytest.raises(ValueError):
        handler = SchedulingRequestHandler(event, MockLambdaContext())
        handler.handle_request()


def test_time_zones(moto_ec2: None, ec2_instance_states: InstanceStates) -> None:
    # ----------------------------EC2 Instances-------------------------#
    schedules: dict[str, InstanceSchedule] = {}
    instances: dict[str, str] = {}

    # all times related to 12:00 UTC
    for tz in [
        "Etc/GMT+12",  # local time: 00:00
        "Etc/GMT+10",  # local time: 02:00
        "Etc/GMT+5",  # local time: 07:00
        "Etc/GMT",  # local time: 12:00
        "Etc/GMT-5",  # local time: 17:00
        "Etc/GMT-10",  # local time: 22:00
        "Etc/GMT-13",  # local time: 01:00
    ]:
        schedule, instance_id = tz_instance(tz)
        schedules[tz] = schedule
        instances[tz] = instance_id
        ec2_instance_states.set_instance_state(instance_id, "running")

    ec2_instance_states.save()
    # ----------------------------Event Definition--------------------------#
    context = build_context(
        current_dt=datetime(2023, 6, 9, 12, 0, 0, tzinfo=timezone.utc),
        schedules=schedules,
    )
    event = build_scheduling_event(context)

    # -------------------run handler------------------------#
    handler = SchedulingRequestHandler(event, MockLambdaContext())
    handler.handle_request()

    # ---------------------validate result---------------------#

    # all instances between 0-12 should be running, all instances between 12-24 should be stopped

    assert get_current_state(instances["Etc/GMT+12"]) == "running"  # local time: 00:00
    assert get_current_state(instances["Etc/GMT+10"]) == "running"  # local time: 02:00
    assert get_current_state(instances["Etc/GMT+5"]) == "running"  # local time: 07:00
    assert get_current_state(instances["Etc/GMT"]) == "stopped"  # local time: 12:00
    assert get_current_state(instances["Etc/GMT-5"]) == "stopped"  # local time: 17:00
    assert get_current_state(instances["Etc/GMT-10"]) == "stopped"  # local time: 22:00
    assert get_current_state(instances["Etc/GMT-13"]) == "running"  # local time: 01:00
