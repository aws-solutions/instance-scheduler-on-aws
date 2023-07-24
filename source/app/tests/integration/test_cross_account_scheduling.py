# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import dataclasses

from mypy_boto3_ec2 import EC2Client

from instance_scheduler.configuration.instance_schedule import InstanceSchedule
from instance_scheduler.handler.scheduling_request import SchedulingRequestHandler
from instance_scheduler.schedulers.instance_states import InstanceStates
from instance_scheduler.util.app_env import AppEnv
from tests.context import MockLambdaContext
from tests.integration.helpers.boto_client_helpers import client_in_account_region
from tests.integration.helpers.ec2_helpers import (
    create_ec2_instances,
    get_current_state,
)
from tests.integration.helpers.schedule_helpers import quick_time
from tests.integration.helpers.scheduling_context_builder import (
    build_context,
    build_scheduling_event,
    default_test_schedule,
)


class LocalizedTestInstance:
    def __init__(
        self,
        schedule: InstanceSchedule,
        account: str = "123456789012",
        region: str = "us-east-1",
    ) -> None:
        self.client: EC2Client = client_in_account_region("ec2", account, region)
        (self.instance_id,) = create_ec2_instances(1, schedule, account, region)

    def current_state(self) -> str:
        return get_current_state(self.instance_id, self.client)


def test_cross_account_cross_region_ec2_scheduling_starts_and_stops_instance(
    moto_ec2: None, ec2_instance_states: InstanceStates, app_env: AppEnv
) -> None:
    account = "222233334444"
    region = "us-west-2"
    (ec2_instance,) = create_ec2_instances(1, default_test_schedule(), account, region)

    # ----------------------------Event Definition--------------------------#
    context = build_context(
        current_dt=quick_time(10, 0, 0),
        region=region,
        schedule_lambda_account=False,
        account_id=account,
    )
    event = build_scheduling_event(context)
    # ----------------------------EC2 Instance-------------------------#
    ec2_client: EC2Client = client_in_account_region("ec2", account, region)
    ec2_client.stop_instances(InstanceIds=[ec2_instance])

    # ------------------------Last Desired State------------------------#
    ec2_instance_states.load(account, region)
    ec2_instance_states.set_instance_state(ec2_instance, "stopped")
    ec2_instance_states.save()

    # ---------------------start---------------------#
    handler = SchedulingRequestHandler(event, MockLambdaContext())
    handler.handle_request()

    assert get_current_state(ec2_instance, ec2_client) == "running"

    # ---------------------stop---------------------#
    context = dataclasses.replace(context, current_dt=quick_time(20, 0, 0))
    event = build_scheduling_event(context)
    handler = SchedulingRequestHandler(event, MockLambdaContext())
    handler.handle_request()

    assert get_current_state(ec2_instance, ec2_client) == "stopped"


def test_cross_account_scheduling_does_not_schedule_other_instances(
    moto_ec2: None, ec2_instance_states: InstanceStates, app_env: AppEnv
) -> None:
    target_account = "222233334444"
    target_region = "us-west-2"

    schedule = InstanceSchedule(
        name="force-stop",
        enforced=True,
        override_status="stopped",
        stop_new_instances=True,
    )

    context = build_context(
        current_dt=quick_time(10, 0, 0),
        region=target_region,
        schedule_lambda_account=False,
        account_id=target_account,
        schedules={schedule.name: schedule},
    )

    event = build_scheduling_event(context)

    target_instance = LocalizedTestInstance(
        schedule, account=target_account, region=target_region
    )
    bad_instances = [
        LocalizedTestInstance(schedule, account=target_account),
        LocalizedTestInstance(schedule, region=target_region),
        LocalizedTestInstance(schedule),
    ]

    handler = SchedulingRequestHandler(event, MockLambdaContext())
    handler.handle_request()

    assert target_instance.current_state() == "stopped"
    for bad_instance in bad_instances:
        assert bad_instance.current_state() == "running"
