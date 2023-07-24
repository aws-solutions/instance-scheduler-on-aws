# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import json
from datetime import datetime, time
from typing import Any
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import boto3
from freezegun import freeze_time
from mypy_boto3_ec2.client import EC2Client

from instance_scheduler.configuration.instance_schedule import InstanceSchedule
from instance_scheduler.configuration.running_period import RunningPeriod
from instance_scheduler.configuration.running_period_dict_element import (
    RunningPeriodDictElement,
)
from instance_scheduler.handler.scheduling_request import SchedulingRequestHandler
from instance_scheduler.ops_metrics import GatheringFrequency
from instance_scheduler.ops_metrics.metric_type.instance_count_metric import (
    InstanceCountMetric,
)
from instance_scheduler.schedulers.instance_states import InstanceStates
from instance_scheduler.util.app_env import AppEnv
from tests import ami
from tests.context import MockLambdaContext
from tests.integration.helpers.schedule_helpers import quick_time
from tests.integration.helpers.scheduling_context_builder import (
    build_context,
    build_scheduling_event,
)
from tests.integration.ops_metrics.conftest import solution_metrics_uuid

schedule_1 = InstanceSchedule(
    name="sched_1",
    periods=[
        RunningPeriodDictElement(
            period=RunningPeriod(name="stop", begintime=time(12, 0, 0))
        )
    ],
)

schedule_2 = InstanceSchedule(
    name="sched_2",
    periods=[
        RunningPeriodDictElement(
            period=RunningPeriod(name="start", endtime=time(12, 0, 0))
        )
    ],
)


def create_test_instances(count: int, schedule: InstanceSchedule) -> list[str]:
    ec2_client: EC2Client = boto3.client("ec2")
    create_response = ec2_client.run_instances(
        ImageId=ami, MinCount=count, MaxCount=count
    )
    instance_ids = [instance["InstanceId"] for instance in create_response["Instances"]]
    ec2_client.create_tags(
        Resources=instance_ids, Tags=[{"Key": "Schedule", "Value": schedule.name}]
    )

    return instance_ids


def get_sent_instance_count_metric(metrics_endpoint: MagicMock) -> Any:
    desired_metric: dict[str, Any] = {}
    for call_args in metrics_endpoint.call_args_list:
        json_payload = call_args[1]["data"]
        sent_metric = json.loads(json_payload)

        if sent_metric["Event_Name"] == "instance_count":
            if desired_metric:
                raise Exception("metric sent multiple times")
            desired_metric = sent_metric

    if not desired_metric:
        raise Exception("metric not found")
    return desired_metric


def test_instance_count_metric_is_daily_metric() -> None:
    assert InstanceCountMetric.collection_frequency is GatheringFrequency.DAILY


@patch("instance_scheduler.schedulers.instance_scheduler.should_collect_metric")
@freeze_time(datetime(2023, 6, 12, 12, 0, 0, tzinfo=ZoneInfo("UTC")))
def test_scheduling_execution_sends_expected_instance_count_metric(
    should_collect_metrics_func: MagicMock,
    mock_metrics_endpoint: MagicMock,
    moto_ec2: None,
    ec2_instance_states: InstanceStates,
    app_env: AppEnv,
) -> None:
    should_collect_metrics_func.return_value = True

    create_test_instances(5, schedule_1)
    create_test_instances(10, schedule_2)

    context = build_context(current_dt=quick_time(10, 0, 0))
    event = build_scheduling_event(context)
    handler = SchedulingRequestHandler(event, MockLambdaContext())
    handler.handle_request()

    expected_metric = {
        "TimeStamp": "2023-06-12 12:00:00",
        "UUID": str(solution_metrics_uuid),
        "Solution": app_env.solution_id,
        "Version": app_env.solution_version,
        "Event_Name": "instance_count",
        "Context": {
            "service": "ec2",
            "region": "us-east-1",
            "num_instances": 15,
            "num_schedules": 2,
        },
    }

    sent_metric = get_sent_instance_count_metric(mock_metrics_endpoint)
    assert sent_metric == expected_metric
