# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import boto3
from mypy_boto3_rds import RDSClient

from instance_scheduler.handler.scheduling_request import SchedulingRequestHandler
from instance_scheduler.schedulers.instance_states import InstanceStates
from tests.context import MockLambdaContext
from tests.integration.helpers.rds_helpers import get_rds_cluster_state
from tests.integration.helpers.schedule_helpers import quick_time
from tests.integration.helpers.scheduling_context_builder import (
    build_context,
    build_scheduling_event,
)


def test_rds_cluster_starts_at_beginning_of_period(
    rds_cluster: str, rds_instance_states: InstanceStates
) -> None:
    context = build_context(
        current_dt=quick_time(10, 0, 0), schedule_clusters=True, service="rds"
    )
    event = build_scheduling_event(context)

    rds_client: RDSClient = boto3.client("rds")
    rds_client.stop_db_cluster(DBClusterIdentifier=rds_cluster)

    rds_instance_states.set_instance_state(rds_cluster, "stopped")
    rds_instance_states.save()

    handler = SchedulingRequestHandler(event, MockLambdaContext())
    handler.handle_request()

    assert get_rds_cluster_state(rds_cluster) == "available"


def test_rds_cluster_stops_at_end_of_period(
    rds_cluster: str, rds_instance_states: InstanceStates
) -> None:
    context = build_context(
        current_dt=quick_time(20, 0, 0), schedule_clusters=True, service="rds"
    )
    event = build_scheduling_event(context)

    assert get_rds_cluster_state(rds_cluster) == "available"

    rds_instance_states.set_instance_state(rds_cluster, "running")
    rds_instance_states.save()

    handler = SchedulingRequestHandler(event, MockLambdaContext())
    handler.handle_request()

    assert get_rds_cluster_state(rds_cluster) == "stopped"
