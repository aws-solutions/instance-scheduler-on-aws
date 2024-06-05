# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from typing import TYPE_CHECKING

import boto3
from mypy_boto3_rds.type_defs import DBClusterMemberTypeDef

from instance_scheduler.schedulers.instance_states import InstanceStates
from tests.integration.helpers.rds_helpers import (
    get_rds_cluster_state,
    get_rds_instance_state,
)
from tests.integration.helpers.run_handler import simple_schedule, target
from tests.integration.helpers.schedule_helpers import quick_time

if TYPE_CHECKING:
    from mypy_boto3_rds.client import RDSClient
else:
    RDSClient = object


def tag_rds_instance(
    instance: DBClusterMemberTypeDef, schedule_name: str, rds_client: RDSClient
) -> None:
    instance_description = rds_client.describe_db_instances(
        DBInstanceIdentifier=instance["DBInstanceIdentifier"]
    )
    arn = instance_description["DBInstances"][0]["DBInstanceArn"]
    rds_client.add_tags_to_resource(
        ResourceName=arn, Tags=[{"Key": "Schedule", "Value": schedule_name}]
    )


def test_rds_cluster_instances_are_not_scheduled_individually(
    rds_cluster: str,
    rds_instance_states: InstanceStates,
) -> None:
    rds_client: RDSClient = boto3.client("rds")

    cluster = rds_client.describe_db_clusters(DBClusterIdentifier=rds_cluster)
    instances = [instance for instance in cluster["DBClusters"][0]["DBClusterMembers"]]

    assert len(instances) > 0  # test would be invalid if there were no instances

    # customer incorrectly tags instances that are members of a cluster
    for instance in instances:
        tag_rds_instance(instance, "some-other-schedule", rds_client)

    with simple_schedule(
        name="some-other-schedule", begintime="10:00", endtime="20:00"
    ) as context:
        # within period (populate state table)
        context.run_scheduling_request_handler(
            dt=quick_time(19, 55), target=target(service="rds")
        )

        # period end (would normally stop)
        context.run_scheduling_request_handler(
            dt=quick_time(20, 0), target=target(service="rds")
        )

        # neither the instances nor the cluster should have been stopped
        # (the cluster is tagged with a different schedule)
        assert get_rds_cluster_state(rds_cluster) == "available"
        for instance in instances:
            assert (
                get_rds_instance_state(instance["DBInstanceIdentifier"]) == "available"
            )
