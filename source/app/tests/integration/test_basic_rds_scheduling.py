# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import json
from datetime import datetime, timezone
from unittest.mock import MagicMock

from instance_scheduler.configuration.scheduling_context import SchedulingContext
from instance_scheduler.scheduling.rds import RdsService
from instance_scheduler.util.session_manager import lambda_execution_role
from tests.integration.helpers.boto_client_helpers import assume_mocked_role
from tests.integration.helpers.event_helpers import extract_events
from tests.integration.helpers.rds_helpers import (
    create_rds_instances,
    get_rds_instance_state,
    start_rds_instances,
    stop_rds_instances,
)
from tests.integration.helpers.run_handler import simple_schedule, target
from tests.integration.helpers.schedule_helpers import quick_time
from tests.test_utils.unordered_list import UnorderedList


def test_rds_starts_at_beginning_of_period(
    rds_instance: str,
    scheduling_context: SchedulingContext,
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
    scheduling_context: SchedulingContext,
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
    scheduling_context: SchedulingContext,
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
    scheduling_context: SchedulingContext,
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
    scheduling_context: SchedulingContext,
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
    scheduling_context: SchedulingContext,
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


def test_rds_instance_is_not_restarted_if_stopped_during_running_period(
    rds_instance: str,
    scheduling_context: SchedulingContext,
) -> None:
    # instance running in period
    with simple_schedule(begintime="10:00", endtime="20:00") as context:
        context.run_scheduling_request_handler(
            dt=quick_time(15, 0, 0), target=target(service="rds")
        )
        assert get_rds_instance_state(rds_instance) == "available"

        # cx stops instance manually
        stop_rds_instances(rds_instance)

        # instance is not restarted
        context.run_scheduling_request_handler(
            dt=quick_time(15, 5, 0), target=target(service="rds")
        )
        assert get_rds_instance_state(rds_instance) == "stopped"


def test_rds_instance_is_restarted_if_schedule_is_enforced(
    rds_instance: str,
    scheduling_context: SchedulingContext,
) -> None:
    with simple_schedule(begintime="10:00", endtime="20:00", enforced=True) as context:
        # instance running in period
        context.run_scheduling_request_handler(
            dt=quick_time(15, 0, 0), target=target(service="rds")
        )
        assert get_rds_instance_state(rds_instance) == "available"

        # cx stops instance manually
        stop_rds_instances(rds_instance)

        # instance is restarted
        context.run_scheduling_request_handler(
            dt=quick_time(15, 5, 0), target=target(service="rds")
        )
        assert get_rds_instance_state(rds_instance) == "available"


def test_rds_instance_is_not_stopped_if_started_outside_running_period(
    rds_instance: str,
    scheduling_context: SchedulingContext,
) -> None:
    stop_rds_instances(rds_instance)

    with simple_schedule(begintime="10:00", endtime="20:00") as context:
        # instance stopped outside period
        context.run_scheduling_request_handler(
            dt=quick_time(22, 0, 0), target=target(service="rds")
        )
        assert get_rds_instance_state(rds_instance) == "stopped"

        # cx starts instance manually
        start_rds_instances(rds_instance)

        # instance is not stopped
        context.run_scheduling_request_handler(
            dt=quick_time(22, 5, 0), target=target(service="rds")
        )
        assert get_rds_instance_state(rds_instance) == "available"


def test_rds_instance_is_stopped_if_started_outside_running_period_when_schedule_is_enforced(
    rds_instance: str,
    scheduling_context: SchedulingContext,
) -> None:
    stop_rds_instances(rds_instance)

    with simple_schedule(begintime="10:00", endtime="20:00", enforced=True) as context:
        # instance stopped outside period
        context.run_scheduling_request_handler(
            dt=quick_time(22, 0, 0), target=target(service="rds")
        )
        assert get_rds_instance_state(rds_instance) == "stopped"

        # cx starts instance manually
        start_rds_instances(rds_instance)

        # instance is stopped
        context.run_scheduling_request_handler(
            dt=quick_time(22, 5, 0), target=target(service="rds")
        )
        assert get_rds_instance_state(rds_instance) == "stopped"


def test_events_sent_when_rds_instance_started(
    rds_instance: str,
    scheduling_context: SchedulingContext,
    mock_hub_events_client: MagicMock,
) -> None:
    stop_rds_instances(rds_instance)
    with simple_schedule(begintime="10:00", endtime="20:00") as context:
        context.run_scheduling_request_handler(
            dt=quick_time(10, 0), target=target(service="rds")
        )
        assert get_rds_instance_state(rds_instance) == "available"

        # Extract events
        sent_events = extract_events(mock_hub_events_client)

        assert sent_events == UnorderedList(
            [
                {
                    "Source": "instance-scheduler",
                    "DetailType": "Scheduling Action",
                    "Resources": [
                        f"arn:aws:rds:us-east-1:123456789012:db:{rds_instance}"
                    ],
                    "Detail": json.dumps(
                        {
                            "account": "123456789012",
                            "region": "us-east-1",
                            "service": "rds",
                            "resource_id": rds_instance,
                            "requested_action": "Start",
                            "action_taken": "Started",
                            "schedule": "test-schedule",
                        }
                    ),
                    "EventBusName": "local-events",
                },
                {
                    "Source": "instance-scheduler",
                    "DetailType": "Scheduling Action",
                    "Resources": [
                        f"arn:aws:rds:us-east-1:123456789012:db:{rds_instance}"
                    ],
                    "Detail": json.dumps(
                        {
                            "account": "123456789012",
                            "region": "us-east-1",
                            "service": "rds",
                            "resource_id": rds_instance,
                            "requested_action": "Start",
                            "action_taken": "Started",
                            "schedule": "test-schedule",
                        }
                    ),
                    "EventBusName": "global-events",
                },
            ]
        )


def test_events_sent_when_rds_instance_stopped(
    rds_instance: str,
    scheduling_context: SchedulingContext,
    mock_hub_events_client: MagicMock,
) -> None:
    with simple_schedule(begintime="10:00", endtime="20:00") as context:
        context.run_scheduling_request_handler(
            dt=quick_time(20, 0), target=target(service="rds")
        )
        assert get_rds_instance_state(rds_instance) == "stopped"

        # Extract events
        sent_events = extract_events(mock_hub_events_client)

        assert sent_events == UnorderedList(
            [
                {
                    "Source": "instance-scheduler",
                    "DetailType": "Scheduling Action",
                    "Resources": [
                        f"arn:aws:rds:us-east-1:123456789012:db:{rds_instance}"
                    ],
                    "Detail": json.dumps(
                        {
                            "account": "123456789012",
                            "region": "us-east-1",
                            "service": "rds",
                            "resource_id": rds_instance,
                            "requested_action": "Stop",
                            "action_taken": "Stopped",
                            "schedule": "test-schedule",
                        }
                    ),
                    "EventBusName": "local-events",
                },
                {
                    "Source": "instance-scheduler",
                    "DetailType": "Scheduling Action",
                    "Resources": [
                        f"arn:aws:rds:us-east-1:123456789012:db:{rds_instance}"
                    ],
                    "Detail": json.dumps(
                        {
                            "account": "123456789012",
                            "region": "us-east-1",
                            "service": "rds",
                            "resource_id": rds_instance,
                            "requested_action": "Stop",
                            "action_taken": "Stopped",
                            "schedule": "test-schedule",
                        }
                    ),
                    "EventBusName": "global-events",
                },
            ]
        )


def test_rds_unschedulable_resource_applies_error_tags(
    rds_instance: str,
    scheduling_context: SchedulingContext,
) -> None:
    stop_rds_instances(rds_instance)

    # Create read replica
    rds_client = assume_mocked_role("123456789012", "us-east-1").client("rds")
    replica_id = "test-read-replica"

    rds_client.create_db_instance_read_replica(
        DBInstanceIdentifier=replica_id,
        SourceDBInstanceIdentifier=rds_instance,
    )

    with simple_schedule(begintime="10:00", endtime="20:00") as context:
        context.run_scheduling_request_handler(
            dt=quick_time(10, 0), target=target(service="rds")
        )
        # Read replicas cannot be scheduled, should apply error tags

    rds_info = RdsService.describe_rds_instances(
        lambda_execution_role(),
        [f"arn:aws:rds:us-east-1:123456789012:db:{rds_instance}"],
    ).__next__()

    assert rds_info.tags["IS-Error"] == "UnsupportedResource"
    assert "read replica" in rds_info.tags["IS-ErrorMessage"]
