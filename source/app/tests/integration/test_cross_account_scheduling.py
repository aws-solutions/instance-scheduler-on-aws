# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from mypy_boto3_ec2 import EC2Client

from instance_scheduler.handler.environments.main_lambda_environment import (
    MainLambdaEnv,
)
from instance_scheduler.schedulers.instance_states import InstanceStates
from tests.integration.helpers.boto_client_helpers import client_in_account_region
from tests.integration.helpers.ec2_helpers import (
    create_ec2_instances,
    get_current_state,
)
from tests.integration.helpers.run_handler import (
    multi_period_schedule,
    simple_schedule,
    target,
)
from tests.integration.helpers.schedule_helpers import quick_time


class LocalizedTestInstance:
    def __init__(
        self,
        schedule_name: str,
        account: str = "123456789012",
        region: str = "us-east-1",
    ) -> None:
        self.client: EC2Client = client_in_account_region("ec2", account, region)
        (self.instance_id,) = create_ec2_instances(1, schedule_name, account, region)

    def current_state(self) -> str:
        return get_current_state(self.instance_id, self.client)


def test_cross_account_cross_region_ec2_scheduling_starts_and_stops_instance(
    ec2_instance_states: InstanceStates,
    test_suite_env: MainLambdaEnv,
) -> None:
    spoke_account = "222233334444"
    spoke_region = "us-west-2"
    ec2_client: EC2Client = client_in_account_region("ec2", spoke_account, spoke_region)

    with simple_schedule(
        name="test-schedule", begintime="10:00", endtime="20:00"
    ) as context:
        (ec2_instance,) = create_ec2_instances(
            1, "test-schedule", spoke_account, spoke_region
        )
        ec2_client.stop_instances(InstanceIds=[ec2_instance])

        # before start of period (populates state table)
        context.run_scheduling_request_handler(
            dt=quick_time(9, 55, 0),
            target=target(account=spoke_account, region=spoke_region),
        )
        assert get_current_state(ec2_instance, ec2_client) == "stopped"

        # start instance
        context.run_scheduling_request_handler(
            dt=quick_time(10, 0, 0),
            target=target(account=spoke_account, region=spoke_region),
        )
        assert get_current_state(ec2_instance, ec2_client) == "running"

        # stop instance
        context.run_scheduling_request_handler(
            dt=quick_time(20, 0, 0),
            target=target(account=spoke_account, region=spoke_region),
        )
        assert get_current_state(ec2_instance, ec2_client) == "stopped"


def test_cross_account_scheduling_does_not_schedule_other_instances(
    ec2_instance_states: InstanceStates,
    test_suite_env: MainLambdaEnv,
) -> None:
    spoke_account = "222233334444"
    spoke_region = "us-west-2"
    with multi_period_schedule(
        name="force-stop",
        period_definitions=[],  # no periods defined
        enforced=True,
        override_status="stopped",
        stop_new_instances=True,
    ) as context:
        target_instance = LocalizedTestInstance(
            "force-stop", account=spoke_account, region=spoke_region
        )
        bad_instances = [
            # omitted account/region values use hub account/region
            LocalizedTestInstance("force-stop", account=spoke_account),
            LocalizedTestInstance("force-stop", region=spoke_region),
            LocalizedTestInstance("force-stop"),
        ]

        context.run_scheduling_request_handler(
            dt=quick_time(10, 0, 0),
            target=target(account=spoke_account, region=spoke_region),
        )

        assert target_instance.current_state() == "stopped"
        for bad_instance in bad_instances:
            assert bad_instance.current_state() == "running"
