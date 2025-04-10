# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from datetime import datetime, timezone

from instance_scheduler.schedulers.instance_states import InstanceStates
from tests.integration.helpers.rds_helpers import (
    create_rds_instances,
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


def test_rds_ignores_preferred_maintenance_window_when_use_maintenance_windows_is_disabled(
    rds_instance_states: InstanceStates,
) -> None:
    (rds_instance,) = create_rds_instances(
        1, preferred_maintenance_window="tue:22:00-tue:23:00"
    )

    # Nov 5, 2024 is a tuesday
    with simple_schedule(
        begintime="10:00", endtime="12:00", use_maintenance_window=False
    ) as context:
        # init and stop instance
        context.run_scheduling_request_handler(
            dt=datetime(2024, 11, 5, 20, 0, 0, tzinfo=timezone.utc),
            target=target(service="rds"),
        )
        assert get_rds_instance_state(rds_instance) == "stopped"

        # starts 10 minutes early
        context.run_scheduling_request_handler(
            dt=datetime(2024, 11, 5, 22, 30, 0, tzinfo=timezone.utc),
            target=target(service="rds"),
        )
        assert get_rds_instance_state(rds_instance) == "stopped"


def test_rds_starts_10_minutes_prior_to_preferred_maintenance_window(
    rds_instance_states: InstanceStates,
) -> None:
    (rds_instance,) = create_rds_instances(
        1, preferred_maintenance_window="tue:22:00-tue:23:00"
    )

    # Nov 5, 2024 is a tuesday
    with simple_schedule(begintime="10:00", endtime="12:00") as context:
        # init and stop instance
        context.run_scheduling_request_handler(
            dt=datetime(2024, 11, 5, 20, 0, 0, tzinfo=timezone.utc),
            target=target(service="rds"),
        )
        assert get_rds_instance_state(rds_instance) == "stopped"

        # starts 10 minutes early
        context.run_scheduling_request_handler(
            dt=datetime(2024, 11, 5, 21, 50, 0, tzinfo=timezone.utc),
            target=target(service="rds"),
        )
        assert get_rds_instance_state(rds_instance) == "available"


def test_rds_starts_10_minutes_prior_to_preferred_maintenance_window_when_delta_would_cross_midnight(
    rds_instance_states: InstanceStates,
) -> None:
    (rds_instance,) = create_rds_instances(
        1, preferred_maintenance_window="tue:00:00-tue:01:00"
    )

    # Nov 5, 2024 is a tuesday
    with simple_schedule(begintime="10:00", endtime="12:00") as context:
        # init and stop instance
        context.run_scheduling_request_handler(
            dt=datetime(2024, 11, 4, 23, 0, 0, tzinfo=timezone.utc),
            target=target(service="rds"),
        )
        assert get_rds_instance_state(rds_instance) == "stopped"

        # starts 10 minutes early
        context.run_scheduling_request_handler(
            dt=datetime(2024, 11, 4, 23, 50, 0, tzinfo=timezone.utc),
            target=target(service="rds"),
        )
        assert get_rds_instance_state(rds_instance) == "available"


def test_rds_stops_at_end_of_preferred_maintenance_window(
    rds_instance_states: InstanceStates,
) -> None:
    (rds_instance,) = create_rds_instances(
        1, preferred_maintenance_window="tue:22:00-tue:23:00"
    )

    # Nov 5, 2024 is a tuesday
    with simple_schedule(begintime="10:00", endtime="12:00") as context:
        # init and stop instance
        context.run_scheduling_request_handler(
            dt=datetime(2024, 11, 5, 20, 0, 0, tzinfo=timezone.utc),
            target=target(service="rds"),
        )
        assert get_rds_instance_state(rds_instance) == "stopped"

        # running during window
        context.run_scheduling_request_handler(
            dt=datetime(2024, 11, 5, 22, 00, 0, tzinfo=timezone.utc),
            target=target(service="rds"),
        )
        assert get_rds_instance_state(rds_instance) == "available"

        context.run_scheduling_request_handler(
            dt=datetime(2024, 11, 5, 22, 59, 0, tzinfo=timezone.utc),
            target=target(service="rds"),
        )
        assert get_rds_instance_state(rds_instance) == "available"

        # stop at end of window
        context.run_scheduling_request_handler(
            dt=datetime(2024, 11, 5, 23, 00, 0, tzinfo=timezone.utc),
            target=target(service="rds"),
        )
        assert get_rds_instance_state(rds_instance) == "stopped"
