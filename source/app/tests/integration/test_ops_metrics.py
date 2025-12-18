# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from datetime import datetime, timezone
from typing import Iterator
from unittest.mock import MagicMock, patch

from _pytest.fixtures import fixture
from freezegun import freeze_time
from instance_scheduler.configuration.scheduling_context import SchedulingContext
from instance_scheduler.observability.cw_ops_insights import (
    CloudWatchOperationalInsights,
)
from instance_scheduler.scheduling.asg.asg_size import AsgSize
from instance_scheduler.scheduling.resource_registration import register_asg_resources
from instance_scheduler.util.session_manager import lambda_execution_role
from mypy_boto3_ec2.literals import InstanceTypeType
from tests.integration.helpers.asg_helpers import create_asg
from tests.integration.helpers.ec2_helpers import (
    create_ec2_instances,
    start_ec2_instances,
    stop_ec2_instances,
)
from tests.integration.helpers.rds_helpers import (
    create_rds_instances,
)
from tests.integration.helpers.run_handler import simple_schedule, target
from tests.integration.helpers.schedule_helpers import quick_time
from tests.test_utils.mock_resource_registration_environment import (
    MockResourceRegistrationEnvironment,
)
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


def test_metrics_not_sent_when_disabled(
    scheduling_context: SchedulingContext,
    mocked_put_metric_data: MagicMock,
) -> None:
    with simple_schedule(begintime="10:00", endtime="20:00") as context:
        context.run_scheduling_request_handler(
            dt=quick_time(12, 0),
            environment=MockSchedulingRequestEnvironment(enable_ops_monitoring=False),
        )

    mocked_put_metric_data.assert_not_called()


@freeze_time("2023-12-28 20:23:37")
def test_ops_monitoring_metrics_sent_to_cw_when_enabled(
    scheduling_context: SchedulingContext,
    mocked_put_metric_data: MagicMock,
) -> None:
    stop_ec2_instances(
        *create_ec2_instances(1, instance_type=small, schedule_name="test-schedule")
    )
    start_ec2_instances(
        *create_ec2_instances(5, instance_type=medium, schedule_name="test-schedule")
    )

    with simple_schedule(begintime="10:00", endtime="20:00") as context:
        context.run_scheduling_request_handler(
            dt=quick_time(12, 0),
            environment=MockSchedulingRequestEnvironment(enable_ops_monitoring=True),
        )

    fixed_time = datetime(2023, 12, 28, 20, 23, 37, tzinfo=timezone.utc)
    expected_metric_data = {
        "Namespace": "my-hub-stack-name:InstanceScheduler",
        "MetricData": UnorderedList(
            [
                # per instance_type data
                {
                    "MetricName": "ManagedInstances",
                    "Dimensions": [
                        {"Name": "Service", "Value": "ec2"},
                        {"Name": "InstanceType", "Value": "t2.micro"},
                        {"Name": "SchedulingInterval", "Value": "5"},
                    ],
                    "Timestamp": fixed_time,
                    "Value": 1,
                    "Unit": "Count",
                },
                {
                    "MetricName": "RunningInstances",
                    "Dimensions": [
                        {"Name": "Service", "Value": "ec2"},
                        {"Name": "InstanceType", "Value": "t2.micro"},
                        {"Name": "SchedulingInterval", "Value": "5"},
                    ],
                    "Timestamp": fixed_time,
                    "Value": 0,
                    "Unit": "Count",
                },
                {
                    "MetricName": "StoppedInstances",
                    "Dimensions": [
                        {"Name": "Service", "Value": "ec2"},
                        {"Name": "InstanceType", "Value": "t2.micro"},
                        {"Name": "SchedulingInterval", "Value": "5"},
                    ],
                    "Timestamp": fixed_time,
                    "Value": 1,
                    "Unit": "Count",
                },
                {
                    "MetricName": "ManagedInstances",
                    "Dimensions": [
                        {"Name": "Service", "Value": "ec2"},
                        {"Name": "InstanceType", "Value": "t2.medium"},
                        {"Name": "SchedulingInterval", "Value": "5"},
                    ],
                    "Timestamp": fixed_time,
                    "Value": 5,
                    "Unit": "Count",
                },
                {
                    "MetricName": "RunningInstances",
                    "Dimensions": [
                        {"Name": "Service", "Value": "ec2"},
                        {"Name": "InstanceType", "Value": "t2.medium"},
                        {"Name": "SchedulingInterval", "Value": "5"},
                    ],
                    "Timestamp": fixed_time,
                    "Value": 5,
                    "Unit": "Count",
                },
                {
                    "MetricName": "StoppedInstances",
                    "Dimensions": [
                        {"Name": "Service", "Value": "ec2"},
                        {"Name": "InstanceType", "Value": "t2.medium"},
                        {"Name": "SchedulingInterval", "Value": "5"},
                    ],
                    "Timestamp": fixed_time,
                    "Value": 0,
                    "Unit": "Count",
                },
            ]
        ),
    }

    _, kwargs = mocked_put_metric_data.call_args
    assert kwargs == expected_metric_data
    mocked_put_metric_data.assert_called_once()


@freeze_time("2023-12-28 20:23:37")
def test_instances_with_unknown_schedule_not_included_in_metrics(
    scheduling_context: SchedulingContext,
    mocked_put_metric_data: MagicMock,
) -> None:
    # Create instances with valid schedule
    start_ec2_instances(
        *create_ec2_instances(2, instance_type=small, schedule_name="test-schedule")
    )
    # Create instances with unknown schedule
    start_ec2_instances(
        *create_ec2_instances(3, instance_type=medium, schedule_name="unknown-schedule")
    )

    with simple_schedule(begintime="10:00", endtime="20:00") as context:
        context.run_scheduling_request_handler(
            dt=quick_time(12, 0),
            environment=MockSchedulingRequestEnvironment(enable_ops_monitoring=True),
        )

    fixed_time = datetime(2023, 12, 28, 20, 23, 37, tzinfo=timezone.utc)
    expected_metric_data = {
        "Namespace": "my-hub-stack-name:InstanceScheduler",
        "MetricData": UnorderedList(
            [
                # per instance_type data - only t2.micro instances (valid schedule)
                {
                    "MetricName": "ManagedInstances",
                    "Dimensions": [
                        {"Name": "Service", "Value": "ec2"},
                        {"Name": "InstanceType", "Value": "t2.micro"},
                        {"Name": "SchedulingInterval", "Value": "5"},
                    ],
                    "Timestamp": fixed_time,
                    "Value": 2,
                    "Unit": "Count",
                },
                {
                    "MetricName": "RunningInstances",
                    "Dimensions": [
                        {"Name": "Service", "Value": "ec2"},
                        {"Name": "InstanceType", "Value": "t2.micro"},
                        {"Name": "SchedulingInterval", "Value": "5"},
                    ],
                    "Timestamp": fixed_time,
                    "Value": 2,
                    "Unit": "Count",
                },
                {
                    "MetricName": "StoppedInstances",
                    "Dimensions": [
                        {"Name": "Service", "Value": "ec2"},
                        {"Name": "InstanceType", "Value": "t2.micro"},
                        {"Name": "SchedulingInterval", "Value": "5"},
                    ],
                    "Timestamp": fixed_time,
                    "Value": 0,
                    "Unit": "Count",
                },
            ]
        ),
    }

    _, kwargs = mocked_put_metric_data.call_args
    assert kwargs == expected_metric_data
    mocked_put_metric_data.assert_called_once()


@freeze_time("2023-12-28 20:23:37")
def test_rds_instances_with_unknown_schedule_not_included_in_metrics(
    scheduling_context: SchedulingContext,
    mocked_put_metric_data: MagicMock,
) -> None:
    # Create RDS instances with valid schedule (already started)
    create_rds_instances(
        2,
        instance_type="db.t3.micro",
        schedule_name="test-schedule",
        id_prefix="valid-rds",
    )
    # Create RDS instances with unknown schedule (already started)
    create_rds_instances(
        3,
        instance_type="db.t3.small",
        schedule_name="unknown-schedule",
        id_prefix="unknown-rds",
    )

    with simple_schedule(begintime="10:00", endtime="20:00") as context:
        context.run_scheduling_request_handler(
            dt=quick_time(12, 0),
            target=target(service="rds"),
            environment=MockSchedulingRequestEnvironment(enable_ops_monitoring=True),
        )

    fixed_time = datetime(2023, 12, 28, 20, 23, 37, tzinfo=timezone.utc)
    expected_metric_data = {
        "Namespace": "my-hub-stack-name:InstanceScheduler",
        "MetricData": UnorderedList(
            [
                # per instance_type data - only db.t3.micro instances (valid schedule)
                {
                    "MetricName": "ManagedInstances",
                    "Dimensions": [
                        {"Name": "Service", "Value": "rds"},
                        {"Name": "InstanceType", "Value": "db.t3.micro"},
                        {"Name": "SchedulingInterval", "Value": "5"},
                    ],
                    "Timestamp": fixed_time,
                    "Value": 2,
                    "Unit": "Count",
                },
                {
                    "MetricName": "RunningInstances",
                    "Dimensions": [
                        {"Name": "Service", "Value": "rds"},
                        {"Name": "InstanceType", "Value": "db.t3.micro"},
                        {"Name": "SchedulingInterval", "Value": "5"},
                    ],
                    "Timestamp": fixed_time,
                    "Value": 2,
                    "Unit": "Count",
                },
                {
                    "MetricName": "StoppedInstances",
                    "Dimensions": [
                        {"Name": "Service", "Value": "rds"},
                        {"Name": "InstanceType", "Value": "db.t3.micro"},
                        {"Name": "SchedulingInterval", "Value": "5"},
                    ],
                    "Timestamp": fixed_time,
                    "Value": 0,
                    "Unit": "Count",
                },
            ]
        ),
    }

    _, kwargs = mocked_put_metric_data.call_args
    assert kwargs == expected_metric_data
    mocked_put_metric_data.assert_called_once()


@freeze_time("2023-12-28 20:23:37")
def test_asg_instances_with_unknown_schedule_not_included_in_metrics(
    scheduling_context: SchedulingContext,
    mocked_put_metric_data: MagicMock,
) -> None:
    register_asg_resources(
        [  # Create ASGs with valid schedule
            create_asg("test-asg-1", AsgSize(1, 2, 3), "test-schedule"),
            create_asg("test-asg-2", AsgSize(0, 1, 2), "test-schedule"),
            # Create ASGs with unknown schedule
            create_asg("unknown-asg-1", AsgSize(2, 3, 4), "unknown-schedule"),
            create_asg("unknown-asg-2", AsgSize(1, 2, 3), "unknown-schedule"),
        ],
        lambda_execution_role(),
        MockResourceRegistrationEnvironment(),
    )

    with simple_schedule(begintime="10:00", endtime="20:00") as context:
        context.run_scheduling_request_handler(
            dt=quick_time(12, 0),
            target=target(service="autoscaling"),
            environment=MockSchedulingRequestEnvironment(enable_ops_monitoring=True),
        )

    fixed_time = datetime(2023, 12, 28, 20, 23, 37, tzinfo=timezone.utc)
    expected_metric_data = {
        "Namespace": "my-hub-stack-name:InstanceScheduler",
        "MetricData": UnorderedList(
            [
                # per instance_type data - ASGs use 'asg' as InstanceType
                {
                    "MetricName": "ManagedInstances",
                    "Dimensions": [
                        {"Name": "Service", "Value": "autoscaling"},
                        {"Name": "InstanceType", "Value": "asg"},
                        {"Name": "SchedulingInterval", "Value": "5"},
                    ],
                    "Timestamp": fixed_time,
                    "Value": 2,
                    "Unit": "Count",
                },
                {
                    "MetricName": "RunningInstances",
                    "Dimensions": [
                        {"Name": "Service", "Value": "autoscaling"},
                        {"Name": "InstanceType", "Value": "asg"},
                        {"Name": "SchedulingInterval", "Value": "5"},
                    ],
                    "Timestamp": fixed_time,
                    "Value": 2,
                    "Unit": "Count",
                },
                {
                    "MetricName": "StoppedInstances",
                    "Dimensions": [
                        {"Name": "Service", "Value": "autoscaling"},
                        {"Name": "InstanceType", "Value": "asg"},
                        {"Name": "SchedulingInterval", "Value": "5"},
                    ],
                    "Timestamp": fixed_time,
                    "Value": 0,
                    "Unit": "Count",
                },
            ]
        ),
    }

    _, kwargs = mocked_put_metric_data.call_args
    assert kwargs == expected_metric_data
    mocked_put_metric_data.assert_called_once()
