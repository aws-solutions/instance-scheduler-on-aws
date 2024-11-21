# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import json
from datetime import datetime
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

from freezegun import freeze_time

from instance_scheduler.handler.scheduling_orchestrator import (
    OrchestrationRequest,
    SchedulingOrchestratorHandler,
)
from instance_scheduler.model.ddb_config_item import DdbConfigItem
from instance_scheduler.model.period_definition import PeriodDefinition
from instance_scheduler.model.period_identifier import PeriodIdentifier
from instance_scheduler.model.schedule_definition import ScheduleDefinition
from instance_scheduler.model.store.ddb_config_item_store import DdbConfigItemStore
from instance_scheduler.model.store.period_definition_store import PeriodDefinitionStore
from instance_scheduler.model.store.schedule_definition_store import (
    ScheduleDefinitionStore,
)
from tests.context import MockLambdaContext
from tests.integration.ops_metrics.conftest import override_should_send_metric
from tests.logger import MockLogger
from tests.test_utils.mock_metrics_environment import MockMetricsEnviron
from tests.test_utils.mock_orchestrator_environment import MockOrchestratorEnvironment
from tests.test_utils.unordered_list import UnorderedList

mockEvent: OrchestrationRequest = {"scheduled_action": "run_orchestrator"}


@patch("instance_scheduler.handler.scheduling_orchestrator.should_collect_metric")
@patch.object(SchedulingOrchestratorHandler, "_run_scheduling_lambda")
@freeze_time(datetime(2023, 6, 12, 12, 0, 0, tzinfo=ZoneInfo("UTC")))
def test_orchestrator_sends_expected_metric(
    run_lambda_func: MagicMock,
    should_collect_metric_func: MagicMock,
    mock_metrics_endpoint: MagicMock,
    schedule_store: ScheduleDefinitionStore,
    period_store: PeriodDefinitionStore,
    config_item_store: DdbConfigItemStore,
) -> None:
    # account configuration
    config_item_store.put(
        DdbConfigItem(
            organization_id="", remote_account_ids=["222233334444", "333344445555"]
        )
    )

    period_store.put(
        PeriodDefinition(name="test-period", begintime="05:00", endtime="06:00")
    )
    period_store.put(
        PeriodDefinition(name="test-period-one-sided-begin", begintime="05:00")
    )
    period_store.put(
        PeriodDefinition(name="test-period-one-sided-end", endtime="06:00")
    )

    # test schedules
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
            ],  # one sided schedule counted once
            timezone="Asia/Hong_Kong",  # should not be counted by tz metric
        )
    )

    orchestrator_env = MockOrchestratorEnvironment(
        scheduler_frequency_minutes=10,
        stop_tags=[],
        start_tags=["non-null tag"],
        enable_schedule_hub_account=True,
        schedule_regions=["us-east-1", "us-west-2"],
        enable_ec2_service=True,
        enable_rds_service=True,
        enable_rds_clusters=True,
        enable_neptune_service=True,
        enable_docdb_service=True,
        enable_asg_service=True,
        enable_aws_organizations=False,
        enable_rds_snapshots=False,
        enable_ec2_ssm_maintenance_windows=True,
        ops_dashboard_enabled=True,
        default_timezone=ZoneInfo("Asia/Hong_Kong"),
    )

    with MockMetricsEnviron(
        send_anonymous_metrics=True
    ) as metrics_environ, override_should_send_metric(True):
        should_collect_metric_func.return_value = (
            True  # override return as this metric is normally sent daily
        )
        handler = SchedulingOrchestratorHandler(
            event=mockEvent,
            context=MockLambdaContext(),
            env=orchestrator_env,
            logger=MockLogger(),
        )
        handler.handle_request()

        expected_metric = {
            "timestamp": "2023-06-12 12:00:00",
            "uuid": str(metrics_environ.metrics_uuid),
            "solution": metrics_environ.solution_id,
            "version": metrics_environ.solution_version,
            "event_name": "deployment_description",
            "context_version": 2,
            "context": {
                "services": UnorderedList(
                    ["ec2", "rds", "rds-clusters", "neptune", "docdb", "asg"]
                ),
                "regions": orchestrator_env.schedule_regions,
                "num_accounts": 3,  # local account + 2 remote
                "num_schedules": 4,
                "num_cfn_schedules": 2,
                "num_one_sided_schedules": 3,
                "default_timezone": "Asia/Hong_Kong",
                "create_rds_snapshots": False,
                "schedule_interval_minutes": 10,
                "memory_size_mb": 128,  # memory size from MockLambdaContext
                "using_organizations": False,
                "enable_ec2_ssm_maintenance_windows": True,
                "ops_dashboard_enabled": orchestrator_env.ops_dashboard_enabled,
                "num_started_tags": 1,
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
                "approximate_lambda_payload_size_bytes": 1084,  # semi-magic
            },
        }

        assert mock_metrics_endpoint.call_count == 1
        json_payload = mock_metrics_endpoint.call_args[1]["body"]
        assert json.loads(json_payload) == expected_metric
