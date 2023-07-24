# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import datetime
from typing import Any
from unittest.mock import MagicMock, patch

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
from tests.context import MockLambdaContext


def get_scheduler_conf_defaults() -> dict[str, Any]:
    return {
        "scheduled_services": ["ec2"],
        "schedule_clusters": False,
        "tag_name": "Schedule",
        "regions": [],
        "default_timezone": "UTC",
        "schedules": {
            "test-schedule": InstanceSchedule(
                name="test-schedule",
                periods=[
                    RunningPeriodDictElement(
                        period=RunningPeriod(
                            name="test-period",
                            begintime=datetime.time(10, 0, 0),
                            endtime=datetime.time(20, 0, 0),
                        )
                    )
                ],
            )
        },
        "trace": "False",
        "enable_ssm_maintenance_windows": False,
        "use_metrics": "False",
        "schedule_lambda_account": True,
        "create_rds_snapshot": False,
        "started_tags": "",
        "stopped_tags": "",
        "scheduler_role_name": "Scheduler-Role",
        "namespace": "dev",
        "organization_id": "",
        "aws_partition": "aws",
        "remote_account_ids": [],
    }


mockEvent: OrchestrationRequest = {"scheduled_action": "run_orchestrator"}


@patch.object(SchedulingOrchestratorHandler, "_run_scheduling_lambda")
def test_no_region_provided_uses_local_region(
    run_scheduling_lambda_func: MagicMock,
) -> None:
    conf = get_scheduler_conf_defaults()
    conf["scheduled_services"] = ["ec2"]
    conf["regions"] = []

    with patch.object(
        SchedulingOrchestratorHandler, "configuration", GlobalConfig(**conf)
    ):
        cloudwatch_handler = SchedulingOrchestratorHandler(
            event=mockEvent, context=MockLambdaContext()
        )
        cloudwatch_handler.handle_request()

        assert run_scheduling_lambda_func.call_count == 1

        scheduling_context = run_scheduling_lambda_func.call_args.args[0]
        assert scheduling_context.schedule_lambda_account is True
        assert scheduling_context.service == "ec2"

        assert scheduling_context.region == "us-east-1"


@patch.object(SchedulingOrchestratorHandler, "_run_scheduling_lambda")
def test_no_service_provided_does_not_run_any_lambdas(
    run_scheduling_lambda_func: MagicMock,
) -> None:
    conf = get_scheduler_conf_defaults()
    conf["scheduled_services"] = []
    conf["regions"] = ["us-east-1"]

    with patch.object(
        SchedulingOrchestratorHandler, "configuration", GlobalConfig(**conf)
    ):
        cloudwatch_handler = SchedulingOrchestratorHandler(
            event=mockEvent, context=MockLambdaContext()
        )
        cloudwatch_handler.handle_request()

        assert run_scheduling_lambda_func.call_count == 0


@patch.object(SchedulingOrchestratorHandler, "_run_scheduling_lambda")
def test_remote_account_only_does_not_schedule_locally(
    run_scheduling_lambda_func: MagicMock,
) -> None:
    conf = get_scheduler_conf_defaults()
    conf["scheduled_services"] = ["ec2"]
    conf["regions"] = ["us-east-1"]
    conf["remote_account_ids"] = ["222233334444"]
    conf["schedule_lambda_account"] = False

    with patch.object(
        SchedulingOrchestratorHandler, "configuration", GlobalConfig(**conf)
    ):
        cloudwatch_handler = SchedulingOrchestratorHandler(
            event=mockEvent, context=MockLambdaContext()
        )
        cloudwatch_handler.handle_request()

        assert run_scheduling_lambda_func.call_count == 1

        scheduling_context = run_scheduling_lambda_func.call_args.args[0]
        assert scheduling_context.schedule_lambda_account is False
        assert scheduling_context.service == "ec2"
        assert scheduling_context.account_id == "222233334444"
        assert scheduling_context.region == "us-east-1"


@patch.object(SchedulingOrchestratorHandler, "_run_scheduling_lambda")
def test_1region_1service_calls_scheduler_x1(
    run_scheduling_lambda_func: MagicMock,
) -> None:
    conf = get_scheduler_conf_defaults()
    conf["scheduled_services"] = ["ec2"]
    conf["regions"] = ["us-east-1"]

    with patch.object(
        SchedulingOrchestratorHandler, "configuration", GlobalConfig(**conf)
    ):
        cloudwatch_handler = SchedulingOrchestratorHandler(
            event=mockEvent, context=MockLambdaContext()
        )
        cloudwatch_handler.handle_request()

        assert run_scheduling_lambda_func.call_count == 1

        scheduling_context = run_scheduling_lambda_func.call_args.args[0]
        assert scheduling_context.region == "us-east-1"
        assert scheduling_context.service == "ec2"


@patch.object(SchedulingOrchestratorHandler, "_run_scheduling_lambda")
def test_2region_1service_calls_scheduler_x2(
    run_scheduling_lambda_func: MagicMock,
) -> None:
    conf = get_scheduler_conf_defaults()
    conf["scheduled_services"] = ["ec2"]
    conf["regions"] = ["us-east-1", "us-east-2"]

    with patch.object(
        SchedulingOrchestratorHandler, "configuration", GlobalConfig(**conf)
    ):
        cloudwatch_handler = SchedulingOrchestratorHandler(
            event=mockEvent, context=MockLambdaContext()
        )
        cloudwatch_handler.handle_request()

        assert run_scheduling_lambda_func.call_count == 2

        # first call
        scheduling_context = run_scheduling_lambda_func.call_args_list[0].args[0]
        assert scheduling_context.region == "us-east-1"
        assert scheduling_context.service == "ec2"

        # second call
        scheduling_context = run_scheduling_lambda_func.call_args_list[1].args[0]
        assert scheduling_context.region == "us-east-2"
        assert scheduling_context.service == "ec2"


@patch.object(SchedulingOrchestratorHandler, "_run_scheduling_lambda")
def test_2accounts_1region_1service_nolocal_calls_scheduler_twice(
    run_scheduling_lambda_func: MagicMock,
) -> None:
    conf = get_scheduler_conf_defaults()
    conf["scheduled_services"] = ["ec2"]
    conf["regions"] = ["us-east-1"]
    conf["schedule_lambda_account"] = False
    conf["remote_account_ids"] = ["222233334444", "333344445555"]

    # awkward behavior:
    # providing local account (as defined in mockEvent) as one of the remote accounts
    # causes scheduling in local-mode  (remote id removed, schedule_lambda_account = true)

    with patch.object(
        SchedulingOrchestratorHandler, "configuration", GlobalConfig(**conf)
    ):
        cloudwatch_handler = SchedulingOrchestratorHandler(
            event=mockEvent, context=MockLambdaContext()
        )
        cloudwatch_handler.handle_request()

        assert run_scheduling_lambda_func.call_count == 2

        # first call
        scheduling_context = run_scheduling_lambda_func.call_args_list[0].args[0]
        assert scheduling_context.region == "us-east-1"
        assert scheduling_context.service == "ec2"
        assert scheduling_context.account_id == "222233334444"
        assert scheduling_context.schedule_lambda_account is False

        # second call
        scheduling_context = run_scheduling_lambda_func.call_args_list[1].args[0]
        assert scheduling_context.region == "us-east-1"
        assert scheduling_context.service == "ec2"
        assert scheduling_context.account_id == "333344445555"
        assert scheduling_context.schedule_lambda_account is False


@patch.object(SchedulingOrchestratorHandler, "_run_scheduling_lambda")
def test_2accounts_1region_1service_with_local_calls_scheduler_x3(
    run_scheduling_lambda_func: MagicMock,
) -> None:
    conf = get_scheduler_conf_defaults()
    conf["scheduled_services"] = ["ec2"]
    conf["regions"] = ["us-east-1"]
    conf["schedule_lambda_account"] = True
    conf["remote_account_ids"] = ["222233334444", "333344445555"]

    with patch.object(
        SchedulingOrchestratorHandler, "configuration", GlobalConfig(**conf)
    ):
        cloudwatch_handler = SchedulingOrchestratorHandler(
            event=mockEvent, context=MockLambdaContext()
        )
        cloudwatch_handler.handle_request()

        assert run_scheduling_lambda_func.call_count == 3

        # first call
        scheduling_context = run_scheduling_lambda_func.call_args_list[0].args[0]
        assert scheduling_context.region == "us-east-1"
        assert scheduling_context.service == "ec2"
        assert scheduling_context.account_id == ""
        assert scheduling_context.schedule_lambda_account is True

        # second call
        scheduling_context = run_scheduling_lambda_func.call_args_list[1].args[0]
        assert scheduling_context.region == "us-east-1"
        assert scheduling_context.service == "ec2"
        assert scheduling_context.account_id == "222233334444"
        assert scheduling_context.schedule_lambda_account is False

        # third call
        scheduling_context = run_scheduling_lambda_func.call_args_list[2].args[0]
        assert scheduling_context.region == "us-east-1"
        assert scheduling_context.service == "ec2"
        assert scheduling_context.account_id == "333344445555"
        assert scheduling_context.schedule_lambda_account is False


@patch.object(SchedulingOrchestratorHandler, "_run_scheduling_lambda")
def test_1region_2service_calls_scheduler_x2(
    run_scheduling_lambda_func: MagicMock,
) -> None:
    conf = get_scheduler_conf_defaults()
    conf["scheduled_services"] = ["ec2", "rds"]
    conf["regions"] = ["us-east-1"]

    with patch.object(
        SchedulingOrchestratorHandler, "configuration", GlobalConfig(**conf)
    ):
        cloudwatch_handler = SchedulingOrchestratorHandler(
            event=mockEvent, context=MockLambdaContext()
        )
        cloudwatch_handler.handle_request()

        assert run_scheduling_lambda_func.call_count == 2

        # first call
        scheduling_context = run_scheduling_lambda_func.call_args_list[0].args[0]
        assert scheduling_context.region == "us-east-1"
        assert scheduling_context.service == "ec2"

        # second call
        scheduling_context = run_scheduling_lambda_func.call_args_list[1].args[0]
        assert scheduling_context.region == "us-east-1"
        assert scheduling_context.service == "rds"


@patch.object(SchedulingOrchestratorHandler, "_run_scheduling_lambda")
def test_3account_3region_3service_calls_scheduler_x27(
    run_scheduling_lambda_func: MagicMock,
) -> None:
    conf = get_scheduler_conf_defaults()
    conf["scheduled_services"] = ["ec2", "rds", "ecs"]
    conf["regions"] = ["us-east-1", "us-east-2", "us-west-1"]
    conf["remote_account_ids"] = ["111122223333", "222233334444", "333344445555"]
    conf["schedule_lambda_account"] = False

    with patch.object(
        SchedulingOrchestratorHandler, "configuration", GlobalConfig(**conf)
    ):
        cloudwatch_handler = SchedulingOrchestratorHandler(
            event=mockEvent, context=MockLambdaContext()
        )
        cloudwatch_handler.handle_request()

        assert run_scheduling_lambda_func.call_count == 27
        for index, call in enumerate(run_scheduling_lambda_func.call_args_list):
            scheduling_context = call.args[0]
            assert scheduling_context.region  # assert exists
            assert scheduling_context.account_id or (
                scheduling_context.schedule_lambda_account is True
            )
            assert scheduling_context.service
