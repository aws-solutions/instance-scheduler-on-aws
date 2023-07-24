# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

import boto3
from mypy_boto3_rds import RDSClient

from instance_scheduler.handler.scheduling_request import SchedulingRequestHandler
from instance_scheduler.schedulers.instance_states import InstanceStates
from tests.context import MockLambdaContext
from tests.integration.helpers.rds_helpers import get_rds_instance_state
from tests.integration.helpers.schedule_helpers import quick_time
from tests.integration.helpers.scheduling_context_builder import (
    build_context,
    build_scheduling_event,
)


def test_rds_starts_at_beginning_of_period(
    rds_instance: str, rds_instance_states: InstanceStates
) -> None:
    """
    ----inputs----
    schedule:
        begintime = 10:00
        endtime = 20:00
    current time: 10:00
    instance: stopped
    last_desired_state: stopped

    ----expect----
    instance: available
    """

    # ----------------------------Event Definition--------------------------#
    context = build_context(current_dt=quick_time(10, 0, 0), service="rds")
    event = build_scheduling_event(context)
    # ----------------------------RDS Instance-------------------------#
    rds_client: RDSClient = boto3.client("rds")
    rds_client.stop_db_instance(DBInstanceIdentifier=rds_instance)

    # ------------------------Last Desired State------------------------#
    rds_instance_states.set_instance_state(rds_instance, "stopped")
    rds_instance_states.save()

    # -------------------run handler------------------------#
    handler = SchedulingRequestHandler(event, MockLambdaContext())
    handler.handle_request()

    # ---------------------validate result---------------------#
    assert get_rds_instance_state(rds_instance) == "available"


def test_rds_stops_at_end_of_period(
    rds_instance: str, rds_instance_states: InstanceStates
) -> None:
    """
    ----inputs----
    schedule:
        begintime = 10:00
        endtime = 20:00
    current time: 10:00
    instance: stopped
    last_desired_state: stopped

    ----expect----
    instance: available
    """

    # ----------------------------Event Definition--------------------------#
    context = build_context(current_dt=quick_time(20, 0, 0), service="rds")
    event = build_scheduling_event(context)
    # ----------------------------RDS Instance-------------------------#
    assert get_rds_instance_state(rds_instance) == "available"  # defaults to available

    # ------------------------Last Desired State------------------------#
    rds_instance_states.set_instance_state(rds_instance, "running")
    rds_instance_states.save()

    # -------------------run handler------------------------#
    handler = SchedulingRequestHandler(event, MockLambdaContext())
    handler.handle_request()

    # ---------------------validate result---------------------#
    assert get_rds_instance_state(rds_instance) == "stopped"
