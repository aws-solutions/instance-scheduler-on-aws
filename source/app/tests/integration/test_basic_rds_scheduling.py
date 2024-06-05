# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

from instance_scheduler.schedulers.instance_states import InstanceStates
from tests.integration.helpers.rds_helpers import (
    get_rds_instance_state,
    stop_rds_instances,
)
from tests.integration.helpers.run_handler import simple_schedule, target
from tests.integration.helpers.schedule_helpers import quick_time


def test_rds_starts_at_beginning_of_period(
    rds_instance: str,
    rds_instance_states: InstanceStates,
) -> None:
    # instance is already stopped
    stop_rds_instances(rds_instance)
    with simple_schedule(begintime="10:00", endtime="20:00") as context:
        # before start of period (populates state table)
        context.run_scheduling_request_handler(
            dt=quick_time(9, 55), target=target(service="rds")
        )
        assert get_rds_instance_state(rds_instance) == "stopped"
        # start of period
        context.run_scheduling_request_handler(
            dt=quick_time(10, 0), target=target(service="rds")
        )
        assert get_rds_instance_state(rds_instance) == "available"


def test_rds_stops_at_end_of_period(
    rds_instance: str,
    rds_instance_states: InstanceStates,
) -> None:
    with simple_schedule(begintime="10:00", endtime="20:00") as context:
        # before start of period (populates state table)
        context.run_scheduling_request_handler(
            dt=quick_time(19, 55), target=target(service="rds")
        )
        assert get_rds_instance_state(rds_instance) == "available"
        # start of period
        context.run_scheduling_request_handler(
            dt=quick_time(20, 0), target=target(service="rds")
        )
        assert get_rds_instance_state(rds_instance) == "stopped"
