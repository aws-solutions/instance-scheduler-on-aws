# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

import boto3
from mypy_boto3_rds import RDSClient
from mypy_boto3_rds.type_defs import DBSnapshotMessageTypeDef

from instance_scheduler.schedulers.instance_states import InstanceStates
from tests.integration.helpers.rds_helpers import get_rds_instance_state
from tests.integration.helpers.run_handler import simple_schedule, target
from tests.integration.helpers.schedule_helpers import quick_time
from tests.test_utils.mock_scheduling_request_environment import (
    MockSchedulingRequestEnvironment,
)


def test_rds_creates_snapshot_when_flag_enabled(
    rds_instance: str,
    rds_instance_states: InstanceStates,
) -> None:
    with simple_schedule(begintime="10:00", endtime="20:00") as context:
        # before end of period (populates state table)
        context.run_scheduling_request_handler(
            dt=quick_time(19, 55, 0), target=target(service="rds")
        )
        assert get_rds_instance_state(rds_instance) == "available"

        # test if snapshot is created
        context.run_scheduling_request_handler(
            dt=quick_time(20, 0, 0),
            environment=MockSchedulingRequestEnvironment(enable_rds_snapshots=True),
            target=target(service="rds"),
        )

        assert (
            get_rds_instance_state(rds_instance) == "stopped"
        )  # ensure instance actually stopped
        rds_client: RDSClient = boto3.client("rds")
        result: DBSnapshotMessageTypeDef = rds_client.describe_db_snapshots(
            DBInstanceIdentifier=rds_instance, SnapshotType="manual"
        )
        assert len(result["DBSnapshots"]) == 1


def test_rds_does_not_create_snapshot_when_flag_disabled(
    rds_instance: str,
    rds_instance_states: InstanceStates,
) -> None:
    with simple_schedule(begintime="10:00", endtime="20:00") as context:
        # before end of period (populates state table)
        context.run_scheduling_request_handler(
            dt=quick_time(19, 55, 0), target=target(service="rds")
        )
        assert get_rds_instance_state(rds_instance) == "available"

        # test if snapshot is not created
        context.run_scheduling_request_handler(
            dt=quick_time(20, 0, 0),
            environment=MockSchedulingRequestEnvironment(enable_rds_snapshots=False),
            target=target(service="rds"),
        )

        assert (
            get_rds_instance_state(rds_instance) == "stopped"
        )  # ensure instance actually stopped
        rds_client: RDSClient = boto3.client("rds")
        result: DBSnapshotMessageTypeDef = rds_client.describe_db_snapshots(
            DBInstanceIdentifier=rds_instance, SnapshotType="manual"
        )
        assert len(result["DBSnapshots"]) == 0
