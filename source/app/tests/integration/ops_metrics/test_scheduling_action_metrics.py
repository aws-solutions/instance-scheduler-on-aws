# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import json
from datetime import datetime, time
from typing import Any
from unittest.mock import ANY, MagicMock, patch
from zoneinfo import ZoneInfo

import boto3
from freezegun import freeze_time
from mypy_boto3_ec2.client import EC2Client
from mypy_boto3_ec2.literals import InstanceTypeType

from instance_scheduler.configuration.instance_schedule import InstanceSchedule
from instance_scheduler.configuration.running_period import RunningPeriod
from instance_scheduler.configuration.running_period_dict_element import (
    RunningPeriodDictElement,
)
from instance_scheduler.handler.scheduling_request import SchedulingRequestHandler
from instance_scheduler.schedulers.instance_states import InstanceStates
from instance_scheduler.util.app_env import AppEnv
from tests.context import MockLambdaContext
from tests.integration.helpers.scheduling_context_builder import (
    build_context,
    build_scheduling_event,
)
from tests.integration.ops_metrics.conftest import solution_metrics_uuid

medium: InstanceTypeType = "a1.medium"
large: InstanceTypeType = "a1.large"

will_start = InstanceSchedule(
    name="start_instances",
    periods=[
        RunningPeriodDictElement(
            period=RunningPeriod(name="stop", begintime=time(12, 0, 0))
        )
    ],
)

will_stop = InstanceSchedule(
    name="stop_instances",
    periods=[
        RunningPeriodDictElement(
            period=RunningPeriod(name="start", endtime=time(12, 0, 0))
        )
    ],
    stop_new_instances=True,
)

will_resize_to_large = InstanceSchedule(
    name="resize_instances",
    periods=[
        RunningPeriodDictElement(
            period=RunningPeriod(
                name="medium_window", begintime=time(6, 0, 0), endtime=time(12, 0, 0)
            ),
            instancetype=medium,
        ),
        RunningPeriodDictElement(
            period=RunningPeriod(name="large_window", begintime=time(12, 0, 0)),
            instancetype=large,
        ),
    ],
)

context = build_context(
    current_dt=datetime(2023, 6, 12, 12, 0, 0, tzinfo=ZoneInfo("UTC")),
    schedules={
        "start_instances": will_start,
        "stop_instances": will_stop,
        "resize_instances": will_resize_to_large,
    },
)


def create_test_instances(
    count: int, instance_type: InstanceTypeType, schedule: InstanceSchedule
) -> list[str]:
    ec2_client: EC2Client = boto3.client("ec2")
    instance_ids = new_ec2_instances_of_type(ec2_client, count, instance_type)
    ec2_client.create_tags(
        Resources=instance_ids, Tags=[{"Key": "Schedule", "Value": schedule.name}]
    )

    if schedule in [will_start, will_resize_to_large]:
        ec2_client.stop_instances(InstanceIds=instance_ids)

    return instance_ids


def new_ec2_instances_of_type(
    ec2_client: EC2Client, count: int, ec2_instance_type: InstanceTypeType
) -> list[str]:
    ami = "ami-0889ff9188674a22a"
    create_response = ec2_client.run_instances(
        ImageId=ami, MinCount=count, MaxCount=count, InstanceType=ec2_instance_type
    )
    instance_ids = [instance["InstanceId"] for instance in create_response["Instances"]]

    return instance_ids


def get_sent_scheduling_action_metric(metrics_endpoint: MagicMock) -> Any:
    desired_metric: dict[str, Any] = {}
    for call_args in metrics_endpoint.call_args_list:
        json_payload = call_args[1]["data"]
        sent_metric = json.loads(json_payload)

        if sent_metric["Event_Name"] == "scheduling_action":
            if desired_metric:
                raise Exception("metric sent multiple times")
            desired_metric = sent_metric

    if not desired_metric:
        raise Exception("metric not found")
    return desired_metric


@patch("instance_scheduler.schedulers.instance_scheduler.should_collect_metric")
@freeze_time(datetime(2023, 6, 12, 12, 0, 0, tzinfo=ZoneInfo("UTC")))
def test_scheduling_execution_sends_expected_actions_metric(
    should_collect_metrics_func: MagicMock,
    mock_metrics_endpoint: MagicMock,
    moto_ec2: None,
    ec2_instance_states: InstanceStates,
    app_env: AppEnv,
) -> None:
    should_collect_metrics_func.return_value = True

    create_test_instances(8, medium, will_start)
    create_test_instances(6, large, will_start)
    create_test_instances(4, medium, will_stop)
    create_test_instances(2, large, will_stop)
    create_test_instances(5, medium, will_resize_to_large)  # instances already stopped

    event = build_scheduling_event(context)
    handler = SchedulingRequestHandler(event, MockLambdaContext())
    handler.handle_request()

    expected_metric = {
        "TimeStamp": "2023-06-12 12:00:00",
        "UUID": str(solution_metrics_uuid),
        "Solution": app_env.solution_id,
        "Version": app_env.solution_version,
        "Event_Name": "scheduling_action",
        "Context": {
            "duration_seconds": ANY,
            "num_instances_scanned": 25,
            "num_unique_schedules": 3,
            "actions": [
                {
                    "action": "Started",
                    "instanceType": "a1.medium",
                    "instances": 8,
                    "service": "ec2",
                },
                {
                    "action": "Started",
                    "instanceType": "a1.large",
                    "instances": 11,  # the 5 instances resized to a1.large were also started
                    "service": "ec2",
                },
                {
                    "action": "Stopped",
                    "instanceType": "a1.medium",
                    "instances": 4,
                    "service": "ec2",
                },
                {
                    "action": "Stopped",
                    "instanceType": "a1.large",
                    "instances": 2,
                    "service": "ec2",
                },
                {
                    "action": "Resized",
                    "instanceType": "a1.medium-a1.large",
                    "instances": 5,
                    "service": "ec2",
                },
            ],
        },
    }

    sent_metric = get_sent_scheduling_action_metric(mock_metrics_endpoint)
    assert sent_metric == expected_metric
    assert sent_metric["Context"]["duration_seconds"] is not None
