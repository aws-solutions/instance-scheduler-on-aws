# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import json
from datetime import datetime
from itertools import chain
from typing import Any
from unittest.mock import ANY, MagicMock
from zoneinfo import ZoneInfo

import pytest
from freezegun import freeze_time
from mypy_boto3_ec2.client import EC2Client
from mypy_boto3_ec2.literals import InstanceTypeType

from instance_scheduler.model.period_definition import PeriodDefinition
from instance_scheduler.model.period_identifier import PeriodIdentifier
from instance_scheduler.model.schedule_definition import ScheduleDefinition
from instance_scheduler.schedulers.instance_states import InstanceStates
from tests.conftest import get_ami
from tests.integration.helpers.ec2_helpers import (
    create_ec2_instances,
    start_ec2_instances,
    stop_ec2_instances,
)
from tests.integration.helpers.run_handler import SchedulingTestContext
from tests.test_utils.mock_metrics_environment import MockMetricsEnviron

medium: InstanceTypeType = "a1.medium"
large: InstanceTypeType = "a1.large"

will_start = ScheduleDefinition(
    name="will_start", periods=[PeriodIdentifier.of("start-at-noon")]
)

will_stop = ScheduleDefinition(
    name="will_stop", periods=[PeriodIdentifier.of("stop-at-noon")]
)

will_resize_to_large = ScheduleDefinition(
    name="will_resize_to_large",
    periods=[PeriodIdentifier.of("start-at-noon", instance_type=large)],
)

periods = [
    PeriodDefinition(name="start-at-noon", begintime="12:00"),
    PeriodDefinition(name="stop-at-noon", endtime="12:00"),
]

context = SchedulingTestContext(
    schedules=[will_start, will_stop, will_resize_to_large],
    periods=periods,
)

dt = datetime(2023, 6, 12, 12, 0, 0, tzinfo=ZoneInfo("UTC"))


def new_ec2_instances_of_type(
    ec2_client: EC2Client, count: int, ec2_instance_type: InstanceTypeType
) -> list[str]:
    create_response = ec2_client.run_instances(
        ImageId=get_ami(),
        MinCount=count,
        MaxCount=count,
        InstanceType=ec2_instance_type,
    )
    instance_ids = [instance["InstanceId"] for instance in create_response["Instances"]]

    return instance_ids


def get_sent_scheduling_action_metric(metrics_endpoint: MagicMock) -> Any:
    desired_metric: dict[str, Any] = {}
    for call_args in metrics_endpoint.call_args_list:
        json_payload = call_args[1]["body"]
        sent_metric = json.loads(json_payload)

        if sent_metric["event_name"] == "scheduling_action":
            if desired_metric:
                raise Exception("metric sent multiple times")
            desired_metric = sent_metric

    if not desired_metric:
        raise Exception("metric not found")
    return desired_metric


def test_scheduling_execution_does_not_send_scheduling_action_metric_when_no_action_taken(
    mock_metrics_endpoint: MagicMock,
) -> None:
    with MockMetricsEnviron(send_anonymous_metrics=True):
        context.run_scheduling_request_handler(dt=dt)

        with pytest.raises(Exception, match="metric not found"):
            get_sent_scheduling_action_metric(mock_metrics_endpoint)


@freeze_time(datetime(2023, 6, 12, 12, 0, 0, tzinfo=ZoneInfo("UTC")))
def test_scheduling_execution_sends_expected_actions_metric(
    mock_metrics_endpoint: MagicMock,
    ec2_instance_states: InstanceStates,
) -> None:
    with MockMetricsEnviron(send_anonymous_metrics=True) as metrics_env:
        stopped_instances = chain(
            create_ec2_instances(
                8, instance_type=medium, schedule_name=will_start.name
            ),
            create_ec2_instances(6, instance_type=large, schedule_name=will_start.name),
            create_ec2_instances(
                5, instance_type=medium, schedule_name=will_resize_to_large.name
            ),
        )
        running_instances = chain(
            create_ec2_instances(4, instance_type=medium, schedule_name=will_stop.name),
            create_ec2_instances(2, instance_type=large, schedule_name=will_stop.name),
        )

        start_ec2_instances(*running_instances)
        stop_ec2_instances(*stopped_instances)

        context.run_scheduling_request_handler(dt=dt)

        expected_metric = {
            "timestamp": "2023-06-12 12:00:00",
            "uuid": str(metrics_env.metrics_uuid),
            "solution": metrics_env.solution_id,
            "version": metrics_env.solution_version,
            "event_name": "scheduling_action",
            "context_version": 1,
            "context": {
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
        assert sent_metric["context"]["duration_seconds"] is not None
