# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import json

from instance_scheduler.configuration.scheduling_context import SchedulingContext
from instance_scheduler.handler.environments.main_lambda_environment import (
    MainLambdaEnv,
)
from mypy_boto3_ec2 import EC2Client
from tests.integration.helpers.boto_client_helpers import assume_mocked_role
from tests.integration.helpers.ec2_helpers import (
    create_ec2_instances,
    get_current_state,
)
from tests.integration.helpers.event_helpers import (
    create_local_event_bus,
    extract_events,
    mock_events_client,
)
from tests.integration.helpers.run_handler import (
    multi_period_schedule,
    simple_schedule,
    target,
)
from tests.integration.helpers.schedule_helpers import quick_time
from tests.test_utils.unordered_list import UnorderedList


class LocalizedTestInstance:
    def __init__(
        self,
        schedule_name: str,
        account: str = "123456789012",
        region: str = "us-east-1",
    ) -> None:
        self.client: EC2Client = assume_mocked_role(account, region).client("ec2")
        (self.instance_id,) = create_ec2_instances(1, schedule_name, account, region)

    def current_state(self) -> str:
        return get_current_state(self.instance_id, self.client)


def test_cross_account_cross_region_ec2_scheduling_starts_and_stops_instance(
    scheduling_context: SchedulingContext,
    test_suite_env: MainLambdaEnv,
) -> None:
    spoke_account = "222233334444"
    spoke_region = "us-west-2"
    target_role = assume_mocked_role(spoke_account, spoke_region)

    create_local_event_bus(target_role)
    ec2_client: EC2Client = target_role.client("ec2")

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
    scheduling_context: SchedulingContext,
    test_suite_env: MainLambdaEnv,
) -> None:
    spoke_account = "222233334444"
    spoke_region = "us-west-2"
    create_local_event_bus(assume_mocked_role(spoke_account, spoke_region))
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


def test_cross_account_cross_region_ec2_scheduling_sends_events(
    scheduling_context: SchedulingContext,
    test_suite_env: MainLambdaEnv,
) -> None:
    with simple_schedule(
        name="test-schedule", begintime="10:00", endtime="20:00"
    ) as context, mock_events_client(
        "us-east-1"
    ) as hub_events_client, mock_events_client(
        "us-west-2"
    ) as spoke_events_client:
        spoke_account = "222233334444"
        spoke_region = "us-west-2"
        ec2_client: EC2Client = assume_mocked_role(spoke_account, spoke_region).client(
            "ec2"
        )

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

        hub_events = extract_events(hub_events_client)
        spoke_events = extract_events(spoke_events_client)

        assert spoke_events == UnorderedList(
            [
                {
                    "Source": "instance-scheduler",
                    "DetailType": "Scheduling Action",
                    "Resources": [
                        f"arn:aws:ec2:us-west-2:222233334444:instance/{ec2_instance}"
                    ],
                    "Detail": json.dumps(
                        {
                            "account": "222233334444",
                            "region": "us-west-2",
                            "service": "ec2",
                            "resource_id": ec2_instance,
                            "requested_action": "Start",
                            "action_taken": "Started",
                            "schedule": "test-schedule",
                        }
                    ),
                    "EventBusName": "local-events",
                }
            ]
        )
        assert hub_events == UnorderedList(
            [
                {
                    "Source": "instance-scheduler",
                    "DetailType": "Scheduling Action",
                    "Resources": [
                        f"arn:aws:ec2:us-west-2:222233334444:instance/{ec2_instance}"
                    ],
                    "Detail": json.dumps(
                        {
                            "account": "222233334444",
                            "region": "us-west-2",
                            "service": "ec2",
                            "resource_id": ec2_instance,
                            "requested_action": "Start",
                            "action_taken": "Started",
                            "schedule": "test-schedule",
                        }
                    ),
                    "EventBusName": "global-events",
                }
            ]
        )
