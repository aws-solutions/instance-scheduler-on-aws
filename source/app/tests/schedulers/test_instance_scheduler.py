# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from zoneinfo import ZoneInfo

from boto3 import Session
from pytest_mock import MockFixture

from instance_scheduler.configuration.instance_schedule import (
    Instance,
    InstanceSchedule,
)
from instance_scheduler.configuration.scheduling_context import SchedulingContext
from instance_scheduler.schedulers.instance_scheduler import InstanceScheduler
from instance_scheduler.schedulers.instance_states import InstanceStates
from instance_scheduler.service import Ec2Service, ServiceArgs
from tests.integration.helpers.schedule_helpers import quick_time
from tests.logger import MockLogger


def context() -> SchedulingContext:
    return SchedulingContext(
        current_dt=quick_time(10, 0, 0),
        service="ec2",
        schedule_clusters=False,
        tag_name="tag",
        region="us-east-1",
        default_timezone=ZoneInfo("UTC"),
        schedules={},
        trace=False,
        enable_ssm_maintenance_windows=False,
        use_metrics=False,
        account_id="111111111111",
        namespace="test",
        aws_partition="aws",
        scheduler_role_name="scheduler-role",
        organization_id="o-0000000000",
        schedule_lambda_account=True,
        create_rds_snapshot=False,
    )


def test_get_desired_state_and_type_1(moto_sts: None, mocker: MockFixture) -> None:
    schedule = InstanceSchedule(
        name="test-1",
        periods=[],
        timezone="UTC",
        override_status=None,
        description=None,
        use_metrics=None,
        stop_new_instances=None,
        use_maintenance_window=False,
        ssm_maintenance_window="",
        enforced=False,
        hibernate=False,
        retain_running=False,
    )
    instance = Instance(
        maintenance_window=schedule,
        account="test",
        region="us-east-1",
        service="ec2",
        id="ut12y21232u",
        allow_resize=True,
        hibernate=False,
        state="running",
        state_name="running",
        is_running=True,
        is_terminated=False,
        current_state="running",
        instancetype="type",
        tags={},
        name="name",
        schedule_name="schedule",
    )
    scheduling_context = context()
    logger = MockLogger()
    ec2_service = Ec2Service(
        ServiceArgs(
            account_id="",
            scheduling_context=scheduling_context,
            logger=logger,
            session=Session(),
            stack_name="",
        )
    )
    scheduler = InstanceScheduler(
        ec2_service,
        scheduling_context,
        InstanceStates("", "", logger),
        "",
        None,
        logger,
    )
    mocker.patch.object(scheduler, "_logger")
    inst_state, _ = scheduler.get_desired_state_and_type(schedule, instance)
    assert inst_state == "stopped"


def test_get_desired_state_and_type_2(moto_sts: None, mocker: MockFixture) -> None:
    schedule = InstanceSchedule(
        name="test-1",
        periods=[],
        timezone="UTC",
        override_status=None,
        description=None,
        use_metrics=None,
        stop_new_instances=None,
        use_maintenance_window=True,
        ssm_maintenance_window="",
        enforced=False,
        hibernate=False,
        retain_running=False,
    )
    instance = Instance(
        maintenance_window=None,
        account="test",
        region="us-east-1",
        service="ec2",
        id="ut12y21232u",
        allow_resize=True,
        hibernate=False,
        state="running",
        state_name="running",
        is_running=True,
        is_terminated=False,
        current_state="running",
        instancetype="type",
        tags={},
        name="name",
        schedule_name="schedule",
    )
    scheduling_context = context()
    logger = MockLogger()
    ec2_service = Ec2Service(
        ServiceArgs(
            account_id="",
            scheduling_context=scheduling_context,
            logger=logger,
            session=Session(),
            stack_name="",
        )
    )
    scheduler = InstanceScheduler(
        ec2_service,
        scheduling_context,
        InstanceStates("", "", logger),
        "",
        None,
        logger,
    )
    mocker.patch.object(scheduler, "_logger")
    inst_state, _ = scheduler.get_desired_state_and_type(schedule, instance)
    assert inst_state == "stopped"
