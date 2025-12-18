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
from instance_scheduler.configuration.scheduling_context import SchedulingContext
from instance_scheduler.model.period_definition import PeriodDefinition
from instance_scheduler.model.period_identifier import PeriodIdentifier
from instance_scheduler.model.schedule_definition import ScheduleDefinition
from instance_scheduler.scheduling.asg.asg_size import AsgSize
from instance_scheduler.scheduling.resource_registration import register_asg_resources
from instance_scheduler.util.session_manager import lambda_execution_role
from mypy_boto3_ec2.client import EC2Client
from mypy_boto3_ec2.literals import InstanceTypeType
from tests.conftest import get_ami
from tests.integration.helpers.asg_helpers import (
    create_asg,
)
from tests.integration.helpers.ec2_helpers import (
    create_ec2_instances,
    start_ec2_instances,
    stop_ec2_instances,
)
from tests.integration.helpers.rds_helpers import (
    create_rds_instances,
    stop_rds_instances,
)
from tests.integration.helpers.run_handler import SchedulingTestContext, target
from tests.test_utils.mock_metrics_environment import MockMetricsEnviron
from tests.test_utils.mock_resource_registration_environment import (
    MockResourceRegistrationEnvironment,
)
from tests.test_utils.unordered_list import UnorderedList

medium: InstanceTypeType = "a1.medium"
large: InstanceTypeType = "a1.large"

will_start = ScheduleDefinition(
    name="will_start", periods=[PeriodIdentifier.of("start-at-noon")]
)

will_stop = ScheduleDefinition(
    name="will_stop", periods=[PeriodIdentifier.of("stop-at-noon")]
)

periods = [
    PeriodDefinition(name="start-at-noon", begintime="12:00"),
    PeriodDefinition(name="stop-at-noon", endtime="12:00"),
]

context = SchedulingTestContext(
    schedules=[will_start, will_stop],
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
    scheduling_context: SchedulingContext,
) -> None:
    with MockMetricsEnviron(send_anonymous_metrics=True):
        context.run_scheduling_request_handler(dt=dt)

        with pytest.raises(Exception, match="metric not found"):
            get_sent_scheduling_action_metric(mock_metrics_endpoint)


@freeze_time(datetime(2023, 6, 12, 12, 0, 0, tzinfo=ZoneInfo("UTC")))
def test_scheduling_execution_sends_expected_actions_metric(
    mock_metrics_endpoint: MagicMock,
    scheduling_context: SchedulingContext,
) -> None:
    with MockMetricsEnviron(send_anonymous_metrics=True) as metrics_env:
        stopped_instances = chain(
            create_ec2_instances(
                8, instance_type=medium, schedule_name=will_start.name
            ),
            create_ec2_instances(6, instance_type=large, schedule_name=will_start.name),
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
            "hub_account_id": metrics_env.hub_account_id,
            "solution": metrics_env.solution_id,
            "version": metrics_env.solution_version,
            "event_name": "scheduling_action",
            "context_version": 2,
            "context": {
                "duration_seconds": ANY,
                "num_instances_scanned": 20,
                "num_unique_schedules": 2,
                "actions": UnorderedList(
                    [
                        {
                            "action": "Started",
                            "instanceType": "a1.medium",
                            "instances": 8,
                            "service": "ec2",
                        },
                        {
                            "action": "Started",
                            "instanceType": "a1.large",
                            "instances": 6,
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
                    ]
                ),
            },
        }

        sent_metric = get_sent_scheduling_action_metric(mock_metrics_endpoint)
        assert sent_metric == expected_metric
        assert sent_metric["context"]["duration_seconds"] is not None


@freeze_time(datetime(2023, 6, 12, 12, 0, 0, tzinfo=ZoneInfo("UTC")))
def test_rds_scheduling_execution_sends_expected_actions_metric(
    mock_metrics_endpoint: MagicMock,
    scheduling_context: SchedulingContext,
) -> None:
    with MockMetricsEnviron(send_anonymous_metrics=True) as metrics_env:
        stopped_instances = create_rds_instances(
            4,
            schedule_name=will_start.name,
            instance_type="db.m5.large",
            id_prefix="test-rds-start",
        )
        create_rds_instances(
            2,
            schedule_name=will_stop.name,
            instance_type="db.m5.large",
            id_prefix="test-rds-stop",
        )

        stop_rds_instances(*stopped_instances)

        context.run_scheduling_request_handler(dt=dt, target=target(service="rds"))

        expected_metric = {
            "timestamp": "2023-06-12 12:00:00",
            "uuid": str(metrics_env.metrics_uuid),
            "hub_account_id": metrics_env.hub_account_id,
            "solution": metrics_env.solution_id,
            "version": metrics_env.solution_version,
            "event_name": "scheduling_action",
            "context_version": 2,
            "context": {
                "duration_seconds": ANY,
                "num_instances_scanned": 6,
                "num_unique_schedules": 2,
                "actions": UnorderedList(
                    [
                        {
                            "action": "Started",
                            "instanceType": "db.m5.large",
                            "instances": 4,
                            "service": "rds",
                        },
                        {
                            "action": "Stopped",
                            "instanceType": "db.m5.large",
                            "instances": 2,
                            "service": "rds",
                        },
                    ]
                ),
            },
        }

        sent_metric = get_sent_scheduling_action_metric(mock_metrics_endpoint)
        assert sent_metric == expected_metric
        assert sent_metric["context"]["duration_seconds"] is not None


@freeze_time(datetime(2023, 6, 12, 12, 0, 0, tzinfo=ZoneInfo("UTC")))
def test_asg_scheduling_execution_sends_expected_actions_metric(
    mock_metrics_endpoint: MagicMock,
    scheduling_context: SchedulingContext,
) -> None:
    with MockMetricsEnviron(send_anonymous_metrics=True) as metrics_env:
        # Create and pre-configure one ASG first

        register_asg_resources(
            [create_asg("test-asg-already-configured", AsgSize(1, 1, 1), will_start)],
            lambda_execution_role(),
            MockResourceRegistrationEnvironment(),
        )
        context.run_scheduling_request_handler(
            dt=dt, target=target(service="autoscaling")
        )

        # Verify first configuration metric
        first_metric = get_sent_scheduling_action_metric(mock_metrics_endpoint)
        assert first_metric["context"]["actions"] == [
            {
                "action": "Configured",
                "instanceType": "asg",
                "instances": 1,
                "service": "autoscaling",
            }
        ]

        # Reset mock for second test
        mock_metrics_endpoint.reset_mock()

        # Create additional ASGs
        register_asg_resources(
            [
                create_asg("test-asg-start-1", AsgSize(0, 0, 0), will_start),
                create_asg("test-asg-start-2", AsgSize(0, 0, 0), will_start),
                create_asg("test-asg-stop-1", AsgSize(1, 2, 3), will_stop),
            ],
            lambda_execution_role(),
            MockResourceRegistrationEnvironment(),
        )

        # Run scheduling again
        context.run_scheduling_request_handler(
            dt=dt, target=target(service="autoscaling")
        )

        expected_metric = {
            "timestamp": "2023-06-12 12:00:00",
            "uuid": str(metrics_env.metrics_uuid),
            "hub_account_id": metrics_env.hub_account_id,
            "solution": metrics_env.solution_id,
            "version": metrics_env.solution_version,
            "event_name": "scheduling_action",
            "context_version": 2,
            "context": {
                "duration_seconds": ANY,
                "num_instances_scanned": 4,
                "num_unique_schedules": 2,
                "actions": UnorderedList(
                    [
                        {
                            "action": "Configured",
                            "instanceType": "asg",
                            "instances": 3,
                            "service": "autoscaling",
                        },
                    ]
                ),
            },
        }

        sent_metric = get_sent_scheduling_action_metric(mock_metrics_endpoint)
        assert sent_metric == expected_metric
        assert sent_metric["context"]["duration_seconds"] is not None

        # Reset mock for third test
        mock_metrics_endpoint.reset_mock()

        # Run scheduling one more time - should not send metric as all ASGs are already configured
        context.run_scheduling_request_handler(
            dt=dt, target=target(service="autoscaling")
        )

        # Should not send metric when no actions are taken (all already configured)
        with pytest.raises(Exception, match="metric not found"):
            get_sent_scheduling_action_metric(mock_metrics_endpoint)
