# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from typing import TYPE_CHECKING

import boto3

from instance_scheduler.handler.scheduling_request import SchedulingRequestHandler
from instance_scheduler.schedulers.instance_states import InstanceStates
from tests.context import MockLambdaContext
from tests.integration.helpers.rds_helpers import (
    get_rds_cluster_state,
    get_rds_instance_state,
)
from tests.integration.helpers.schedule_helpers import quick_time
from tests.integration.helpers.scheduling_context_builder import (
    build_context,
    build_scheduling_event,
)

if TYPE_CHECKING:
    from mypy_boto3_rds.client import RDSClient
else:
    RDSClient = object


def test_rds_cluster_instance_not_scheduled(
    rds_cluster: str, rds_instance_states: InstanceStates
) -> None:
    """Instances part of an aurora cluster should not be scheduled, even if tagged"""
    context = build_context(
        current_dt=quick_time(10, 0, 0), schedule_clusters=False, service="rds"
    )
    event = build_scheduling_event(context)

    rds_client: RDSClient = boto3.client("rds")

    cluster = rds_client.describe_db_clusters(DBClusterIdentifier=rds_cluster)
    instances = [instance for instance in cluster["DBClusters"][0]["DBClusterMembers"]]

    assert instances
    for instance in instances:
        instance_description = rds_client.describe_db_instances(
            DBInstanceIdentifier=instance["DBInstanceIdentifier"]
        )
        arn = instance_description["DBInstances"][0]["DBInstanceArn"]
        rds_client.add_tags_to_resource(
            ResourceName=arn, Tags=[{"Key": "Schedule", "Value": "test-schedule"}]
        )
        rds_client.stop_db_instance(
            DBInstanceIdentifier=instance["DBInstanceIdentifier"]
        )

    rds_client.stop_db_cluster(DBClusterIdentifier=rds_cluster)

    rds_instance_states.set_instance_state(rds_cluster, "stopped")
    rds_instance_states.save()

    handler = SchedulingRequestHandler(event, MockLambdaContext())
    handler.handle_request()

    assert get_rds_cluster_state(rds_cluster) == "stopped"
    for instance in instances:
        assert get_rds_instance_state(instance["DBInstanceIdentifier"]) == "stopped"
