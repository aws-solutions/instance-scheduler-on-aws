# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import json
from datetime import datetime
from typing import Any
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

from freezegun import freeze_time

from instance_scheduler.model.period_definition import PeriodDefinition
from instance_scheduler.model.period_identifier import PeriodIdentifier
from instance_scheduler.model.schedule_definition import ScheduleDefinition
from instance_scheduler.ops_metrics import GatheringFrequency
from instance_scheduler.ops_metrics.metric_type.instance_count_metric import (
    InstanceCountMetric,
)
from instance_scheduler.schedulers.instance_states import InstanceStates
from tests.integration.helpers.ec2_helpers import create_ec2_instances
from tests.integration.helpers.run_handler import SchedulingTestContext
from tests.integration.helpers.schedule_helpers import quick_time
from tests.integration.ops_metrics.conftest import override_should_send_metric
from tests.test_utils.mock_metrics_environment import MockMetricsEnviron

schedule_1 = ScheduleDefinition(
    name="sched_1", periods=[PeriodIdentifier.of("period1")]
)

schedule_2 = ScheduleDefinition(
    name="sched_2", periods=[PeriodIdentifier.of("period1")]
)

periods = [PeriodDefinition(name="period1", begintime="10:00", endtime="20:00")]


def get_sent_instance_count_metric(metrics_endpoint: MagicMock) -> Any:
    desired_metric: dict[str, Any] = {}
    for call_args in metrics_endpoint.call_args_list:
        json_payload = call_args[1]["body"]
        sent_metric = json.loads(json_payload)

        if sent_metric["event_name"] == "instance_count":
            if desired_metric:
                raise Exception("metric sent multiple times")
            desired_metric = sent_metric

    if not desired_metric:
        raise Exception("metric not found")
    return desired_metric


def test_instance_count_metric_is_daily_metric() -> None:
    assert InstanceCountMetric.collection_frequency is GatheringFrequency.DAILY


@freeze_time(datetime(2023, 6, 12, 12, 0, 0, tzinfo=ZoneInfo("UTC")))
def test_scheduling_execution_sends_expected_instance_count_metric(
    mock_metrics_endpoint: MagicMock,
    ec2_instance_states: InstanceStates,
) -> None:
    with MockMetricsEnviron(
        send_anonymous_metrics=True
    ) as metrics_environment, override_should_send_metric(True):
        create_ec2_instances(5, schedule_1.name)
        create_ec2_instances(10, schedule_2.name)
        create_ec2_instances(
            3, "invalid"
        )  # these should be ignored as their schedules are invalid/missing

        context = SchedulingTestContext(
            schedules=[schedule_1, schedule_2], periods=periods
        )
        context.run_scheduling_request_handler(dt=quick_time(10, 0))

        expected_metric = {
            "timestamp": "2023-06-12 12:00:00",
            "uuid": str(metrics_environment.metrics_uuid),
            "solution": metrics_environment.solution_id,
            "version": metrics_environment.solution_version,
            "event_name": "instance_count",
            "context_version": 1,
            "context": {
                "service": "ec2",
                "region": "us-east-1",
                "num_instances": 15,
                "num_schedules": 2,
            },
        }

        sent_metric = get_sent_instance_count_metric(mock_metrics_endpoint)
        assert sent_metric == expected_metric
