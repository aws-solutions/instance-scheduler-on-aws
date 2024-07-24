# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

from instance_scheduler.handler.environments.main_lambda_environment import (
    MainLambdaEnv,
)
from instance_scheduler.schedulers.instance_states import InstanceStates
from tests.integration.helpers.rds_helpers import (
    get_rds_cluster_state,
    stop_rds_clusters,
)
from tests.integration.helpers.run_handler import simple_schedule, target
from tests.integration.helpers.schedule_helpers import quick_time


def test_rds_cluster_starts_at_beginning_of_period(
    rds_cluster: str,
    rds_instance_states: InstanceStates,
) -> None:
    with simple_schedule(begintime="10:00", endtime="20:00") as context:
        stop_rds_clusters(rds_cluster)

        # before start of period (populates state table)
        context.run_scheduling_request_handler(
            dt=quick_time(9, 55), target=target(service="rds")
        )
        assert get_rds_cluster_state(rds_cluster) == "stopped"

        # start of period
        context.run_scheduling_request_handler(
            dt=quick_time(10, 0), target=target(service="rds")
        )
        assert get_rds_cluster_state(rds_cluster) == "available"


def test_rds_cluster_stops_at_end_of_period(
    rds_cluster: str,
    rds_instance_states: InstanceStates,
    test_suite_env: MainLambdaEnv,
) -> None:
    with simple_schedule(begintime="10:00", endtime="20:00") as context:
        # before end of period (populates state table)
        context.run_scheduling_request_handler(
            dt=quick_time(19, 55), target=target(service="rds")
        )
        assert get_rds_cluster_state(rds_cluster) == "available"

        # end of period
        context.run_scheduling_request_handler(
            dt=quick_time(20, 0), target=target(service="rds")
        )
        assert get_rds_cluster_state(rds_cluster) == "stopped"
