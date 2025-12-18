# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import json
from datetime import datetime
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

from freezegun import freeze_time
from instance_scheduler.configuration.scheduling_context import SchedulingContext
from instance_scheduler.handler.heartbeat_metrics_reporter import (
    report_heartbeat_metric,
)
from instance_scheduler.model.managed_instance import (
    RegisteredEc2Instance,
    RegisteredRdsInstance,
)
from instance_scheduler.model.period_definition import PeriodDefinition
from instance_scheduler.model.period_identifier import PeriodIdentifier
from instance_scheduler.model.schedule_definition import ScheduleDefinition
from instance_scheduler.scheduling.states import InstanceState
from instance_scheduler.util.arn import ARN
from tests.context import MockLambdaContext
from tests.integration.ops_metrics.conftest import override_should_send_metric
from tests.test_utils.mock_heartbeat_metrics_environment import (
    MockHeartbeatMetricsEnvironment,
)
from tests.test_utils.mock_metrics_environment import MockMetricsEnviron
from tests.test_utils.unordered_list import UnorderedList


@freeze_time(datetime(2023, 6, 12, 12, 0, 0, tzinfo=ZoneInfo("UTC")))
def test_heartbeat_reporter_sends_expected_metric(
    mock_metrics_endpoint: MagicMock,
    scheduling_context: SchedulingContext,
) -> None:
    period_store = scheduling_context.period_store
    schedule_store = scheduling_context.schedule_store
    registry = scheduling_context.registry

    period_store.put(
        PeriodDefinition(name="test-period", begintime="05:00", endtime="06:00")
    )
    period_store.put(
        PeriodDefinition(name="test-period-one-sided-begin", begintime="05:00")
    )
    period_store.put(
        PeriodDefinition(name="test-period-one-sided-end", endtime="06:00")
    )

    schedule_store.put(
        ScheduleDefinition(
            name="all-flags",
            periods=[PeriodIdentifier.of("test-period")],
            override_status="running",
            stop_new_instances=True,
            ssm_maintenance_window=["test-window"],
            enforced=True,
            hibernate=True,
            retain_running=True,
            timezone="Asia/Hong_Kong",
        )
    )
    schedule_store.put(
        ScheduleDefinition(
            name="no-flags-cfn",
            periods=[PeriodIdentifier.of("test-period-one-sided-begin")],
            configured_in_stack="some-stack-arn",
            stop_new_instances=False,
            timezone="UTC",
        )
    )
    schedule_store.put(
        ScheduleDefinition(
            name="non-default-tz-cfn",
            periods=[
                PeriodIdentifier.of("test-period"),
                PeriodIdentifier.of("test-period-one-sided-begin"),
            ],
            configured_in_stack="some-stack-arn",
            timezone="UTC",
        )
    )
    schedule_store.put(
        ScheduleDefinition(
            name="explicit-tz-matches-default",
            periods=[
                PeriodIdentifier.of("test-period-one-sided-begin"),
                PeriodIdentifier.of("test-period-one-sided-end"),
            ],
            timezone="Asia/Hong_Kong",
        )
    )

    registry.put(
        RegisteredEc2Instance(
            account="111122223333",
            region="us-east-1",
            resource_id="i-1234567890abcdef0",
            arn=ARN("arn:aws:ec2:us-east-1:111122223333:instance/i-1234567890abcdef0"),
            schedule="all-flags",
            name="test-instance-1",
            stored_state=InstanceState.RUNNING,
        )
    )
    registry.put(
        RegisteredEc2Instance(
            account="111122223333",
            region="us-east-1",
            resource_id="i-1234567890abcdef1",
            arn=ARN("arn:aws:ec2:us-east-1:111122223333:instance/i-1234567890abcdef1"),
            schedule="explicit-tz-matches-default",
            name="test-instance-3",
            stored_state=InstanceState.STOPPED,
        )
    )
    registry.put(
        RegisteredEc2Instance(
            account="222233334444",
            region="us-west-2",
            resource_id="i-0987654321fedcba0",
            arn=ARN("arn:aws:ec2:us-west-2:222233334444:instance/i-0987654321fedcba0"),
            schedule="no-flags-cfn",
            name="test-instance-2",
            stored_state=InstanceState.STOPPED,
        )
    )
    registry.put(
        RegisteredRdsInstance(
            account="333344445555",
            region="us-east-1",
            resource_id="db-instance-1",
            arn=ARN("arn:aws:rds:us-east-1:333344445555:db:db-instance-1"),
            schedule="non-default-tz-cfn",
            name="test-db-1",
            stored_state=InstanceState.RUNNING,
        )
    )

    with MockMetricsEnviron(
        send_anonymous_metrics=True
    ) as metrics_environ, override_should_send_metric(
        True
    ), MockHeartbeatMetricsEnvironment().patch_env():
        report_heartbeat_metric({}, MockLambdaContext())

        expected_metric = {
            "timestamp": "2023-06-12 12:00:00",
            "uuid": str(metrics_environ.metrics_uuid),
            "hub_account_id": metrics_environ.hub_account_id,
            "solution": metrics_environ.solution_id,
            "version": metrics_environ.solution_version,
            "event_name": "deployment_description",
            "context_version": 3,
            "context": {
                "services": UnorderedList(["ec2", "rds"]),
                "regions": UnorderedList(["us-east-1", "us-west-2"]),
                "num_accounts": 3,
                "num_resources": 4,
                "num_targets": 3,
                "num_schedules": 4,
                "num_cfn_schedules": 2,
                "num_one_sided_schedules": 3,
                "default_timezone": "UTC",
                "create_rds_snapshots": False,
                "schedule_interval_minutes": 5,
                "memory_size_mb": 128,
                "using_organizations": False,
                "enable_ec2_ssm_maintenance_windows": False,
                "ops_dashboard_enabled": False,
                "num_started_tags": 0,
                "num_stopped_tags": 0,
                "schedule_flag_counts": {
                    "stop_new_instances": 3,
                    "enforced": 1,
                    "retain_running": 1,
                    "hibernate": 1,
                    "override": 1,
                    "use_ssm_maintenance_window": 1,
                    "non_default_timezone": 2,
                },
                "approximate_lambda_payload_size_bytes": 0,
            },
        }

        # Should send 1 deployment description metric + 3 instance count metrics (one per target)
        assert mock_metrics_endpoint.call_count == 4

        # Find the deployment description metric
        deployment_metric = None
        instance_count_metrics = []
        for call_args in mock_metrics_endpoint.call_args_list:
            json_payload = call_args[1]["body"]
            sent_metric = json.loads(json_payload)
            if sent_metric["event_name"] == "deployment_description":
                deployment_metric = sent_metric
            elif sent_metric["event_name"] == "instance_count":
                instance_count_metrics.append(sent_metric)

        assert deployment_metric == expected_metric

        # Verify instance count metrics
        expected_instance_metrics = [
            {
                "timestamp": "2023-06-12 12:00:00",
                "uuid": str(metrics_environ.metrics_uuid),
                "hub_account_id": metrics_environ.hub_account_id,
                "solution": metrics_environ.solution_id,
                "version": metrics_environ.solution_version,
                "event_name": "instance_count",
                "context_version": 2,
                "context": {
                    "account": "111122223333",
                    "service": "ec2",
                    "region": "us-east-1",
                    "num_instances": 2,
                    "num_schedules": 2,
                },
            },
            {
                "timestamp": "2023-06-12 12:00:00",
                "uuid": str(metrics_environ.metrics_uuid),
                "hub_account_id": metrics_environ.hub_account_id,
                "solution": metrics_environ.solution_id,
                "version": metrics_environ.solution_version,
                "event_name": "instance_count",
                "context_version": 2,
                "context": {
                    "account": "222233334444",
                    "service": "ec2",
                    "region": "us-west-2",
                    "num_instances": 1,
                    "num_schedules": 1,
                },
            },
            {
                "timestamp": "2023-06-12 12:00:00",
                "uuid": str(metrics_environ.metrics_uuid),
                "hub_account_id": metrics_environ.hub_account_id,
                "solution": metrics_environ.solution_id,
                "version": metrics_environ.solution_version,
                "event_name": "instance_count",
                "context_version": 2,
                "context": {
                    "account": "333344445555",
                    "service": "rds",
                    "region": "us-east-1",
                    "num_instances": 1,
                    "num_schedules": 1,
                },
            },
        ]

        assert len(instance_count_metrics) == 3
        assert UnorderedList(instance_count_metrics) == UnorderedList(
            expected_instance_metrics
        )
