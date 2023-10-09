# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import json
from datetime import datetime, time
from os import environ
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

from freezegun import freeze_time

from instance_scheduler.configuration.instance_schedule import InstanceSchedule
from instance_scheduler.configuration.running_period import RunningPeriod
from instance_scheduler.configuration.running_period_dict_element import (
    RunningPeriodDictElement,
)
from instance_scheduler.configuration.scheduler_config import GlobalConfig
from instance_scheduler.handler.scheduling_orchestrator import (
    OrchestrationRequest,
    SchedulingOrchestratorHandler,
)
from instance_scheduler.util.app_env import AppEnv
from tests.context import MockLambdaContext
from tests.integration.ops_metrics.conftest import solution_metrics_uuid

mockEvent: OrchestrationRequest = {"scheduled_action": "run_orchestrator"}

periods: list[RunningPeriodDictElement] = [
    RunningPeriodDictElement(
        period=RunningPeriod(
            name="test-period",
            begintime=time(10, 0, 0),
            endtime=time(20, 0, 0),
        )
    )
]

global_config = GlobalConfig(
    scheduled_services=["ec2", "rds"],
    schedule_clusters=False,
    tag_name="Schedule",
    regions=["us-east-1", "us-east-2", "us-west-2"],
    default_timezone=ZoneInfo("Asia/Hong_Kong"),
    schedules={
        "all-flags": InstanceSchedule(
            name="all-flags",
            periods=periods,
            override_status="running",
            use_metrics=True,
            stop_new_instances=True,
            use_maintenance_window=True,
            enforced=True,
            hibernate=True,
            retain_running=True,
            timezone="Asia/Hong_Kong",
        ),
        "no-flags-cfn": InstanceSchedule(
            name="no-flags-cfn",
            periods=periods,
            configured_in_stack="some-stack-arn",
            timezone="UTC",
        ),
        "non-default-tz-cfn": InstanceSchedule(
            name="non-default-tz-cfn",
            periods=periods,
            configured_in_stack="some-stack-arn",
            timezone="UTC",
        ),
        "explicit-tz-matches-default": InstanceSchedule(
            name="explicit-tz-matches-default",
            periods=periods,
            timezone="Asia/Hong_Kong",  # should not be counted by tz metric
        ),
    },
    trace=False,
    enable_ssm_maintenance_windows=True,
    use_metrics=True,
    schedule_lambda_account=True,
    create_rds_snapshot=False,
    started_tags="non-null tag",
    stopped_tags="",
    scheduler_role_name="Scheduler-Role",
    namespace="dev",
    organization_id="",
    aws_partition="aws",
    remote_account_ids=["222233334444", "333344445555"],
)

env = {
    "START_TAGS": "non-null tag",
    "STOP_TAGS": "",
    "SCHEDULER_FREQUENCY": "10",
    "ENABLE_AWS_ORGANIZATIONS": "False",
    "ENABLE_EC2_SSM_MAINTENANCE_WINDOWS": "True",
}


@patch("instance_scheduler.handler.scheduling_orchestrator.should_collect_metric")
@patch.object(SchedulingOrchestratorHandler, "_run_scheduling_lambda")
@patch.dict(environ, env)
@freeze_time(datetime(2023, 6, 12, 12, 0, 0, tzinfo=ZoneInfo("UTC")))
def test_orchestrator_sends_expected_metric(
    run_lambda_func: MagicMock,
    should_collect_metric_func: MagicMock,
    mock_metrics_endpoint: MagicMock,
    app_env: AppEnv,
) -> None:
    should_collect_metric_func.return_value = True
    with patch.object(SchedulingOrchestratorHandler, "configuration", global_config):
        handler = SchedulingOrchestratorHandler(
            event=mockEvent, context=MockLambdaContext()
        )
        handler.handle_request()

        expected_metric = {
            "TimeStamp": "2023-06-12 12:00:00",
            "UUID": str(solution_metrics_uuid),
            "Solution": app_env.solution_id,
            "Version": app_env.solution_version,
            "Event_Name": "deployment_description",
            "Context": {
                "services": ["ec2", "rds"],
                "regions": ["us-east-1", "us-east-2", "us-west-2"],
                "num_accounts": 3,  # local account + 2 remote
                "num_schedules": 4,
                "num_cfn_schedules": 2,
                "default_timezone": "Asia/Hong_Kong",
                "schedule_aurora_clusters": False,
                "create_rds_snapshots": False,
                "schedule_interval_minutes": 10,
                "memory_size_mb": 128,  # memory size from MockLambdaContext
                "using_organizations": False,
                "enable_ec2_ssm_maintenance_windows": True,
                "num_started_tags": 1,
                "num_stopped_tags": 0,
                "schedule_flag_counts": {
                    "stop_new_instances": 1,
                    "enforced": 1,
                    "retain_running": 1,
                    "hibernate": 1,
                    "override": 1,
                    "use_ssm_maintenance_window": 1,
                    "use_metrics": 1,
                    "non_default_timezone": 2,
                },
            },
        }

        assert mock_metrics_endpoint.call_count == 1
        json_payload = mock_metrics_endpoint.call_args[1]["data"]
        assert json.loads(json_payload) == expected_metric
