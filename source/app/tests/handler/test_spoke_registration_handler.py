# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import json

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
from tests.test_utils.mock_spoke_registration_environment import (
    MockSpokeRegistrationEnvironment,
)
from tests.test_utils.unordered_list import UnorderedList


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
