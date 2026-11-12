# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import json

import boto3
import pytest
from instance_scheduler.model.store.resource_registry import ResourceRegistry
from instance_scheduler.model.store.schedule_definition_store import (
    ScheduleDefinitionStore,
)
from instance_scheduler.scheduling.asg.asg_size import AsgSize
from tests.context import MockLambdaContext
from tests.integration.helpers.asg_helpers import create_asg
from tests.integration.helpers.boto_client_helpers import assume_mocked_role
from tests.integration.helpers.ec2_helpers import create_ec2_instances
from tests.integration.helpers.event_helpers import extract_events, mock_events_client
from tests.integration.helpers.rds_helpers import (
    create_rds_clusters,
    create_rds_instances,
)
from tests.test_utils.mock_environs.mock_spoke_registration_environment import (
    MockSpokeRegistrationEnvironment,
)
from tests.test_utils.unordered_list import UnorderedList

SPOKE_ACCOUNT = "123456789012"
SSM_PARAM_PATH = MockSpokeRegistrationEnvironment().ssm_param_path_name


def set_registration_state(region: str, state: str) -> None:
    # simulates the spoke's region registration custom resource, which writes this
    # parameter in its own account before invoking the spoke registration handler
    boto3.client("ssm").put_parameter(
        Name=f"{SSM_PARAM_PATH}/{region}",
        Value=state,
        Type="String",
        Overwrite=True,
    )


def get_registration_state(region: str) -> str:
    return str(
        boto3.client("ssm").get_parameter(Name=f"{SSM_PARAM_PATH}/{region}")[
            "Parameter"
        ]["Value"]
    )


def registered_ec2_count(resource_registry: ResourceRegistry, region: str) -> int:
    return len(
        list(resource_registry.find_by_scheduling_target(SPOKE_ACCOUNT, region, "ec2"))
    )


def test_registration_request_adds_resources_to_registry(
    resource_registry: ResourceRegistry,
    registry_table: str,
    local_event_bus: str,
    global_event_bus: str,
) -> None:
    with MockSpokeRegistrationEnvironment().patch_env():
        from instance_scheduler.handler.spoke_registration import lambda_handler

        # Create test resources
        create_ec2_instances(2, "test-schedule")
        create_rds_instances(1, "test-schedule")
        create_rds_clusters(1, "test-schedule")
        set_registration_state("us-east-1", "created")

        event = {
            "account": "123456789012",
            "region": "us-east-1",
            "operation": "Register",
        }

        lambda_handler(event, MockLambdaContext())

        # Verify resources were added to registry
        registered_resources = list(
            resource_registry.find_by_scheduling_target(
                "123456789012", "us-east-1", "ec2"
            )
        )
        assert len(registered_resources) == 2

        registered_rds = list(
            resource_registry.find_by_scheduling_target(
                "123456789012", "us-east-1", "rds"
            )
        )
        assert len(registered_rds) == 2


def test_registration_sends_registration_events(
    resource_registry: ResourceRegistry,
    registry_table: str,
    schedule_store: ScheduleDefinitionStore,
) -> None:
    spoke_region = "us-east-2"

    with MockSpokeRegistrationEnvironment().patch_env(), mock_events_client() as hub_events_client, mock_events_client(
        spoke_region
    ) as spoke_events_client:
        from instance_scheduler.handler.spoke_registration import lambda_handler

        # Create test resources
        (ec2_inst,) = create_ec2_instances(1, "test-schedule", region=spoke_region)
        (rds_db,) = create_rds_instances(1, "test-schedule", region=spoke_region)
        (rds_cluster,) = create_rds_clusters(1, "test-schedule", region=spoke_region)
        asg = create_asg(
            "test-asg",
            AsgSize(1, 2, 3),
            "test-schedule",
            role=assume_mocked_role(region=spoke_region),
        )
        set_registration_state(spoke_region, "created")

        event = {
            "account": "123456789012",
            "region": "us-east-2",
            "operation": "Register",
        }

        lambda_handler(event, MockLambdaContext())

        hub_events = extract_events(hub_events_client)

        assert hub_events == UnorderedList(
            [
                {
                    "Source": "instance-scheduler",
                    "DetailType": "Resource Registered",
                    "Resources": [
                        f"arn:aws:ec2:us-east-2:123456789012:instance/{ec2_inst}"
                    ],
                    "Detail": json.dumps(
                        {
                            "account": "123456789012",
                            "region": "us-east-2",
                            "service": "ec2",
                            "resource_id": ec2_inst,
                            "schedule": "test-schedule",
                        }
                    ),
                    "EventBusName": "global-events",
                },
                {
                    "Source": "instance-scheduler",
                    "DetailType": "Resource Registered",
                    "Resources": [f"arn:aws:rds:us-east-2:123456789012:db:{rds_db}"],
                    "Detail": json.dumps(
                        {
                            "account": "123456789012",
                            "region": "us-east-2",
                            "service": "rds",
                            "resource_id": rds_db,
                            "schedule": "test-schedule",
                        }
                    ),
                    "EventBusName": "global-events",
                },
                {
                    "Source": "instance-scheduler",
                    "DetailType": "Resource Registered",
                    "Resources": [
                        f"arn:aws:rds:us-east-2:123456789012:cluster:{rds_cluster}"
                    ],
                    "Detail": json.dumps(
                        {
                            "account": "123456789012",
                            "region": "us-east-2",
                            "service": "rds",
                            "resource_id": rds_cluster,
                            "schedule": "test-schedule",
                        }
                    ),
                    "EventBusName": "global-events",
                },
                {
                    "Source": "instance-scheduler",
                    "DetailType": "Resource Registered",
                    "Resources": [asg.arn],
                    "Detail": json.dumps(
                        {
                            "account": "123456789012",
                            "region": "us-east-2",
                            "service": "autoscaling",
                            "resource_id": asg.resource_id,
                            "schedule": "test-schedule",
                        }
                    ),
                    "EventBusName": "global-events",
                },
            ]
        )

        spoke_events = extract_events(spoke_events_client)

        assert spoke_events == UnorderedList(
            [
                {
                    "Source": "instance-scheduler",
                    "DetailType": "Resource Registered",
                    "Resources": [
                        f"arn:aws:ec2:us-east-2:123456789012:instance/{ec2_inst}"
                    ],
                    "Detail": json.dumps(
                        {
                            "account": "123456789012",
                            "region": "us-east-2",
                            "service": "ec2",
                            "resource_id": ec2_inst,
                            "schedule": "test-schedule",
                        }
                    ),
                    "EventBusName": "local-events",
                },
                {
                    "Source": "instance-scheduler",
                    "DetailType": "Resource Registered",
                    "Resources": [f"arn:aws:rds:us-east-2:123456789012:db:{rds_db}"],
                    "Detail": json.dumps(
                        {
                            "account": "123456789012",
                            "region": "us-east-2",
                            "service": "rds",
                            "resource_id": rds_db,
                            "schedule": "test-schedule",
                        }
                    ),
                    "EventBusName": "local-events",
                },
                {
                    "Source": "instance-scheduler",
                    "DetailType": "Resource Registered",
                    "Resources": [
                        f"arn:aws:rds:us-east-2:123456789012:cluster:{rds_cluster}"
                    ],
                    "Detail": json.dumps(
                        {
                            "account": "123456789012",
                            "region": "us-east-2",
                            "service": "rds",
                            "resource_id": rds_cluster,
                            "schedule": "test-schedule",
                        }
                    ),
                    "EventBusName": "local-events",
                },
                {
                    "Source": "instance-scheduler",
                    "DetailType": "Resource Registered",
                    "Resources": [asg.arn],
                    "Detail": json.dumps(
                        {
                            "account": "123456789012",
                            "region": "us-east-2",
                            "service": "autoscaling",
                            "resource_id": asg.resource_id,
                            "schedule": "test-schedule",
                        }
                    ),
                    "EventBusName": "local-events",
                },
            ]
        )


def test_registration_marks_region_as_managed(
    resource_registry: ResourceRegistry,
    registry_table: str,
    local_event_bus: str,
    global_event_bus: str,
) -> None:
    with MockSpokeRegistrationEnvironment().patch_env():
        from instance_scheduler.handler.spoke_registration import lambda_handler

        set_registration_state("us-east-1", "created")
        lambda_handler(
            {"account": SPOKE_ACCOUNT, "region": "us-east-1", "operation": "Register"},
            MockLambdaContext(),
        )

        assert get_registration_state("us-east-1") == "managed"


def test_registration_retry_is_accepted_while_registering(
    resource_registry: ResourceRegistry,
    registry_table: str,
    local_event_bus: str,
    global_event_bus: str,
) -> None:
    with MockSpokeRegistrationEnvironment().patch_env():
        from instance_scheduler.handler.spoke_registration import lambda_handler

        create_ec2_instances(1, "test-schedule")
        set_registration_state("us-east-1", "registering")
        lambda_handler(
            {"account": SPOKE_ACCOUNT, "region": "us-east-1", "operation": "Register"},
            MockLambdaContext(),
        )

        assert registered_ec2_count(resource_registry, "us-east-1") == 1


@pytest.mark.parametrize("state", [None, "managed", "deleting", "deleted"])
def test_registration_is_rejected_when_not_requested_by_target_account(
    state: str | None,
    resource_registry: ResourceRegistry,
    registry_table: str,
    local_event_bus: str,
    global_event_bus: str,
) -> None:
    with MockSpokeRegistrationEnvironment().patch_env():
        from instance_scheduler.handler.spoke_registration import (
            InvalidRequestException,
            lambda_handler,
        )

        create_ec2_instances(1, "test-schedule")
        if state is not None:
            set_registration_state("us-east-1", state)

        with pytest.raises(InvalidRequestException):
            lambda_handler(
                {
                    "account": SPOKE_ACCOUNT,
                    "region": "us-east-1",
                    "operation": "Register",
                },
                MockLambdaContext(),
            )

        assert registered_ec2_count(resource_registry, "us-east-1") == 0
        if state is not None:
            assert get_registration_state("us-east-1") == state


def test_deregistration_removes_resources_when_requested_by_target_account(
    resource_registry: ResourceRegistry,
    registry_table: str,
    local_event_bus: str,
    global_event_bus: str,
) -> None:
    with MockSpokeRegistrationEnvironment().patch_env():
        from instance_scheduler.handler.spoke_registration import lambda_handler

        create_ec2_instances(2, "test-schedule")
        set_registration_state("us-east-1", "created")
        lambda_handler(
            {"account": SPOKE_ACCOUNT, "region": "us-east-1", "operation": "Register"},
            MockLambdaContext(),
        )
        assert registered_ec2_count(resource_registry, "us-east-1") == 2

        set_registration_state("us-east-1", "deleting")
        lambda_handler(
            {
                "account": SPOKE_ACCOUNT,
                "region": "us-east-1",
                "operation": "Deregister",
            },
            MockLambdaContext(),
        )

        assert registered_ec2_count(resource_registry, "us-east-1") == 0
        assert get_registration_state("us-east-1") == "deleted"


@pytest.mark.parametrize("state", [None, "created", "registering", "managed"])
def test_deregistration_is_rejected_when_not_requested_by_target_account(
    state: str | None,
    resource_registry: ResourceRegistry,
    registry_table: str,
    local_event_bus: str,
    global_event_bus: str,
) -> None:
    with MockSpokeRegistrationEnvironment().patch_env():
        from instance_scheduler.handler.spoke_registration import (
            InvalidRequestException,
            lambda_handler,
        )

        create_ec2_instances(2, "test-schedule")
        set_registration_state("us-east-1", "created")
        lambda_handler(
            {"account": SPOKE_ACCOUNT, "region": "us-east-1", "operation": "Register"},
            MockLambdaContext(),
        )
        assert registered_ec2_count(resource_registry, "us-east-1") == 2

        ssm = boto3.client("ssm")
        if state is None:
            ssm.delete_parameter(Name=f"{SSM_PARAM_PATH}/us-east-1")
        else:
            set_registration_state("us-east-1", state)

        # forged deregistration request naming this account
        with pytest.raises(InvalidRequestException):
            lambda_handler(
                {
                    "account": SPOKE_ACCOUNT,
                    "region": "us-east-1",
                    "operation": "Deregister",
                },
                MockLambdaContext(),
            )

        assert registered_ec2_count(resource_registry, "us-east-1") == 2
        if state is not None:
            assert get_registration_state("us-east-1") == state
