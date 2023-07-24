# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

import boto3
from mypy_boto3_rds import RDSClient
from mypy_boto3_rds.type_defs import DBSnapshotMessageTypeDef

from instance_scheduler.handler.scheduling_request import SchedulingRequestHandler
from instance_scheduler.schedulers.instance_states import InstanceStates
from tests.context import MockLambdaContext
from tests.integration.helpers.rds_helpers import get_rds_instance_state
from tests.integration.helpers.schedule_helpers import quick_time
from tests.integration.helpers.scheduling_context_builder import (
    build_context,
    build_scheduling_event,
)


def test_rds_creates_snapshot_when_flag_enabled(
    rds_instance: str, rds_instance_states: InstanceStates
) -> None:
    # ----------------------------Event Definition--------------------------#

    context = build_context(
        current_dt=quick_time(20, 0, 0), service="rds", create_rds_snapshot=True
    )
    event = build_scheduling_event(context)

    # ----------------------------RDS Instance-------------------------#
    # already setup and running
    # ------------------------Last Desired State------------------------#
    rds_instance_states.set_instance_state(rds_instance, "running")
    rds_instance_states.save()
    # -------------------run handler------------------------#
    handler = SchedulingRequestHandler(event, MockLambdaContext())
    handler.handle_request()

    # ---------------------validate result---------------------#
    assert (
        get_rds_instance_state(rds_instance) == "stopped"
    )  # ensure instance actually stopped
    rds_client: RDSClient = boto3.client("rds")
    result: DBSnapshotMessageTypeDef = rds_client.describe_db_snapshots(
        DBInstanceIdentifier=rds_instance
    )
    assert len(result["DBSnapshots"]) == 1


def test_rds_does_not_create_snapshot_when_flag_disabled(
    rds_instance: str, rds_instance_states: InstanceStates
) -> None:
    # ----------------------------Event Definition--------------------------#
    context = build_context(
        current_dt=quick_time(20, 0, 0), service="rds", create_rds_snapshot=False
    )
    event = build_scheduling_event(context)
    # ----------------------------RDS Instance-------------------------#
    # already setup and running
    # ------------------------Last Desired State------------------------#
    rds_instance_states.set_instance_state(rds_instance, "running")
    rds_instance_states.save()
    # -------------------run handler------------------------#
    handler = SchedulingRequestHandler(event, MockLambdaContext())
    handler.handle_request()

    # ---------------------validate result---------------------#
    assert (
        get_rds_instance_state(rds_instance) == "stopped"
    )  # ensure instance actually stopped
    rds_client: RDSClient = boto3.client("rds")
    result: DBSnapshotMessageTypeDef = rds_client.describe_db_snapshots(
        DBInstanceIdentifier=rds_instance
    )
    assert len(result["DBSnapshots"]) == 0
