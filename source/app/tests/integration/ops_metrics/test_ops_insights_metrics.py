# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import json
from datetime import datetime
from typing import Any, Iterator
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest
from _pytest.fixtures import fixture
from freezegun import freeze_time
from mypy_boto3_ec2.literals import InstanceTypeType

from instance_scheduler.ops_metrics import GatheringFrequency
from instance_scheduler.ops_metrics.metric_type.insights_metric import InsightsMetric
from instance_scheduler.ops_monitoring.cw_ops_insights import (
    CloudWatchOperationalInsights,
)
from tests.integration.helpers.ec2_helpers import (
    create_ec2_instances,
    start_ec2_instances,
    stop_ec2_instances,
)
from tests.integration.helpers.run_handler import simple_schedule
from tests.integration.helpers.schedule_helpers import quick_time
from tests.integration.ops_metrics.conftest import override_should_send_metric
from tests.test_utils.mock_metrics_environment import MockMetricsEnviron
from tests.test_utils.mock_scheduling_request_environment import (
    MockSchedulingRequestEnvironment,
)
from tests.test_utils.unordered_list import UnorderedList

# ec2 instance types
small: InstanceTypeType = "t2.micro"
medium: InstanceTypeType = "t2.medium"
large: InstanceTypeType = "t2.large"


@fixture
def mocked_put_metric_data() -> Iterator[MagicMock]:
    with patch.object(
        CloudWatchOperationalInsights, "cloudwatch_client"
    ) as cloudwatch_client:
        with patch.object(cloudwatch_client, "put_metric_data") as put_metric_func:
            yield put_metric_func


class MetricNotFound(Exception):
    pass


def get_sent_ops_insight_metric_json(metrics_endpoint: MagicMock) -> Any:
    desired_metric: dict[str, Any] = {}
    for call_args in metrics_endpoint.call_args_list:
        json_payload = call_args[1]["body"]
        sent_metric = json.loads(json_payload)

        if sent_metric["event_name"] == "insights_metric":
            if desired_metric:
                raise Exception("metric sent multiple times")
            desired_metric = sent_metric

    if not desired_metric:
        raise MetricNotFound("metric not found")
    return desired_metric


def test_op_metric_is_sent_unlimited() -> None:
    assert InsightsMetric.collection_frequency == GatheringFrequency.UNLIMITED


@pytest.mark.skip("insights metrics are currently disabled")
@freeze_time(datetime(2023, 6, 12, 12, 0, 0, tzinfo=ZoneInfo("UTC")))
def test_op_metrics_sent_to_internal_metrics_endpoint(
    state_table: str,
    mock_metrics_endpoint: MagicMock,
    mocked_put_metric_data: MagicMock,
) -> None:
    stop_ec2_instances(
        *create_ec2_instances(1, instance_type=small, schedule_name="test-schedule")
    )
    start_ec2_instances(
        *create_ec2_instances(5, instance_type=medium, schedule_name="test-schedule")
    )

    with (
        MockMetricsEnviron(send_anonymous_metrics=True) as metrics_environ,
        override_should_send_metric(True),
        simple_schedule(begintime="10:00", endtime="20:00") as context,
    ):
        context.run_scheduling_request_handler(dt=quick_time(12, 0))
        expected_metric = {
            "timestamp": "2023-06-12 12:00:00",
            "uuid": str(metrics_environ.metrics_uuid),
            "solution": metrics_environ.solution_id,
            "version": metrics_environ.solution_version,
            "event_name": "insights_metric",
            "context_version": 1,
            "context": {
                "metric_data": UnorderedList(
                    [
                        {
                            "metric_name": "ManagedInstances",
                            "dimensions": [
                                {"name": "Service", "value": "ec2"},
                                {"name": "InstanceType", "value": "t2.micro"},
                                {"name": "SchedulingInterval", "value": "5"},
                            ],
                            "timestamp": "2023-06-12T12:00:00+00:00",
                            "value": 1,
                            "unit": "Count",
                        },
                        {
                            "metric_name": "RunningInstances",
                            "dimensions": [
                                {"name": "Service", "value": "ec2"},
                                {"name": "InstanceType", "value": "t2.micro"},
                                {"name": "SchedulingInterval", "value": "5"},
                            ],
                            "timestamp": "2023-06-12T12:00:00+00:00",
                            "value": 0,
                            "unit": "Count",
                        },
                        {
                            "metric_name": "StoppedInstances",
                            "dimensions": [
                                {"name": "Service", "value": "ec2"},
                                {"name": "InstanceType", "value": "t2.micro"},
                                {"name": "SchedulingInterval", "value": "5"},
                            ],
                            "timestamp": "2023-06-12T12:00:00+00:00",
                            "value": 1,
                            "unit": "Count",
                        },
                        {
                            "metric_name": "ManagedInstances",
                            "dimensions": [
                                {"name": "Service", "value": "ec2"},
                                {"name": "InstanceType", "value": "t2.medium"},
                                {"name": "SchedulingInterval", "value": "5"},
                            ],
                            "timestamp": "2023-06-12T12:00:00+00:00",
                            "value": 5,
                            "unit": "Count",
                        },
                        {
                            "metric_name": "RunningInstances",
                            "dimensions": [
                                {"name": "Service", "value": "ec2"},
                                {"name": "InstanceType", "value": "t2.medium"},
                                {"name": "SchedulingInterval", "value": "5"},
                            ],
                            "timestamp": "2023-06-12T12:00:00+00:00",
                            "value": 5,
                            "unit": "Count",
                        },
                        {
                            "metric_name": "StoppedInstances",
                            "dimensions": [
                                {"name": "Service", "value": "ec2"},
                                {"name": "InstanceType", "value": "t2.medium"},
                                {"name": "SchedulingInterval", "value": "5"},
                            ],
                            "timestamp": "2023-06-12T12:00:00+00:00",
                            "value": 0,
                            "unit": "Count",
                        },
                    ]
                ),
            },
        }
    sent_metric = get_sent_ops_insight_metric_json(mock_metrics_endpoint)
    assert sent_metric == expected_metric


@pytest.mark.skip("insights metrics are currently disabled")
@freeze_time(datetime(2023, 6, 12, 12, 0, 0, tzinfo=ZoneInfo("UTC")))
def test_aws_metrics_still_sent_when_internal_metrics_are_disabled(
    state_table: str,
    mock_metrics_endpoint: MagicMock,
    mocked_put_metric_data: MagicMock,
) -> None:
    stop_ec2_instances(
        *create_ec2_instances(1, instance_type=small, schedule_name="test-schedule")
    )
    start_ec2_instances(
        *create_ec2_instances(5, instance_type=medium, schedule_name="test-schedule")
    )

    with (
        MockMetricsEnviron(send_anonymous_metrics=True) as metrics_environ,
        override_should_send_metric(True),
        simple_schedule(begintime="10:00", endtime="20:00") as context,
    ):
        context.run_scheduling_request_handler(
            dt=quick_time(12, 0),
            environment=MockSchedulingRequestEnvironment(enable_ops_monitoring=False),
        )
        expected_metric = {
            "timestamp": "2023-06-12 12:00:00",
            "uuid": str(metrics_environ.metrics_uuid),
            "solution": metrics_environ.solution_id,
            "version": metrics_environ.solution_version,
            "event_name": "insights_metric",
            "context_version": 1,
            "context": {
                "metric_data": UnorderedList(
                    [
                        {
                            "metric_name": "ManagedInstances",
                            "dimensions": [
                                {"name": "Service", "value": "ec2"},
                                {"name": "InstanceType", "value": "t2.micro"},
                                {"name": "SchedulingInterval", "value": "5"},
                            ],
                            "timestamp": "2023-06-12T12:00:00+00:00",
                            "value": 1,
                            "unit": "Count",
                        },
                        {
                            "metric_name": "RunningInstances",
                            "dimensions": [
                                {"name": "Service", "value": "ec2"},
                                {"name": "InstanceType", "value": "t2.micro"},
                                {"name": "SchedulingInterval", "value": "5"},
                            ],
                            "timestamp": "2023-06-12T12:00:00+00:00",
                            "value": 0,
                            "unit": "Count",
                        },
                        {
                            "metric_name": "StoppedInstances",
                            "dimensions": [
                                {"name": "Service", "value": "ec2"},
                                {"name": "InstanceType", "value": "t2.micro"},
                                {"name": "SchedulingInterval", "value": "5"},
                            ],
                            "timestamp": "2023-06-12T12:00:00+00:00",
                            "value": 1,
                            "unit": "Count",
                        },
                        {
                            "metric_name": "ManagedInstances",
                            "dimensions": [
                                {"name": "Service", "value": "ec2"},
                                {"name": "InstanceType", "value": "t2.medium"},
                                {"name": "SchedulingInterval", "value": "5"},
                            ],
                            "timestamp": "2023-06-12T12:00:00+00:00",
                            "value": 5,
                            "unit": "Count",
                        },
                        {
                            "metric_name": "RunningInstances",
                            "dimensions": [
                                {"name": "Service", "value": "ec2"},
                                {"name": "InstanceType", "value": "t2.medium"},
                                {"name": "SchedulingInterval", "value": "5"},
                            ],
                            "timestamp": "2023-06-12T12:00:00+00:00",
                            "value": 5,
                            "unit": "Count",
                        },
                        {
                            "metric_name": "StoppedInstances",
                            "dimensions": [
                                {"name": "Service", "value": "ec2"},
                                {"name": "InstanceType", "value": "t2.medium"},
                                {"name": "SchedulingInterval", "value": "5"},
                            ],
                            "timestamp": "2023-06-12T12:00:00+00:00",
                            "value": 0,
                            "unit": "Count",
                        },
                    ]
                ),
            },
        }

    sent_metric = get_sent_ops_insight_metric_json(mock_metrics_endpoint)
    assert sent_metric == expected_metric


@freeze_time(datetime(2023, 6, 12, 12, 0, 0, tzinfo=ZoneInfo("UTC")))
def test_aws_metrics_not_sent_when_aws_metrics_disabled(
    state_table: str,
    mock_metrics_endpoint: MagicMock,
    mocked_put_metric_data: MagicMock,
) -> None:
    stop_ec2_instances(
        *create_ec2_instances(1, instance_type=small, schedule_name="test-schedule")
    )

    with simple_schedule(begintime="10:00", endtime="20:00") as context:
        context.run_scheduling_request_handler(
            dt=quick_time(12, 0),
            environment=MockSchedulingRequestEnvironment(enable_ops_monitoring=False),
        )

    with pytest.raises(MetricNotFound):
        get_sent_ops_insight_metric_json(mock_metrics_endpoint)
