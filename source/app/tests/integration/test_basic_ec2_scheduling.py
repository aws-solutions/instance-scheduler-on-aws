# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import json
from unittest.mock import MagicMock

from instance_scheduler.configuration.scheduling_context import SchedulingContext
from instance_scheduler.model.store.resource_registry import ResourceRegistry
from tests.integration.helpers.ec2_helpers import (
    get_current_state,
    start_ec2_instances,
    stop_ec2_instances,
)
from tests.integration.helpers.event_helpers import extract_events
from tests.integration.helpers.run_handler import simple_schedule
from tests.integration.helpers.schedule_helpers import quick_time
from tests.test_utils.unordered_list import UnorderedList


def test_ec2_starts_at_beginning_of_period(
    ec2_instance: str,
    scheduling_context: SchedulingContext,
) -> None:
    # instance is already stopped
    stop_ec2_instances(ec2_instance)
    with simple_schedule(begintime="10:00", endtime="20:00") as context:
        # before start of period (populates state table)
        context.run_scheduling_request_handler(dt=quick_time(9, 55))
        assert get_current_state(ec2_instance) == "stopped"
        # start of period
        context.run_scheduling_request_handler(dt=quick_time(10, 0))
        assert get_current_state(ec2_instance) == "running"


def test_ec2_stops_at_end_of_period(
    ec2_instance: str,
    scheduling_context: SchedulingContext,
) -> None:
    with simple_schedule(begintime="10:00", endtime="20:00") as context:
        # run before end of period (populates state table)
        context.run_scheduling_request_handler(dt=quick_time(19, 55, 0))
        assert get_current_state(ec2_instance) == "running"
        # run at end of period
        context.run_scheduling_request_handler(dt=quick_time(20, 0, 0))
        assert get_current_state(ec2_instance) == "stopped"


def test_instance_is_not_restarted_if_stopped_during_running_period(
    ec2_instance: str,
    scheduling_context: SchedulingContext,
    resource_registry: ResourceRegistry,
) -> None:
    # instance running in period
    with simple_schedule(begintime="10:00", endtime="20:00") as context:
        context.run_scheduling_request_handler(dt=quick_time(15, 0, 0))
        assert get_current_state(ec2_instance) == "running"

        # cx stops instance manually
        stop_ec2_instances(ec2_instance)

        # instance is not restarted
        context.run_scheduling_request_handler(dt=quick_time(15, 5, 0))

        assert get_current_state(ec2_instance) == "stopped"


def test_instance_is_restarted_if_schedule_is_enforced(
    ec2_instance: str,
    scheduling_context: SchedulingContext,
) -> None:
    with simple_schedule(begintime="10:00", endtime="20:00", enforced=True) as context:
        # instance running in period
        context.run_scheduling_request_handler(dt=quick_time(15, 0, 0))
        assert get_current_state(ec2_instance) == "running"

        # cx stops instance manually
        stop_ec2_instances(ec2_instance)

        # instance is restarted
        context.run_scheduling_request_handler(dt=quick_time(15, 5, 0))
        assert get_current_state(ec2_instance) == "running"


def test_instance_is_not_stopped_if_started_outside_running_period(
    ec2_instance: str,
    scheduling_context: SchedulingContext,
) -> None:
    stop_ec2_instances(ec2_instance)

    with simple_schedule(begintime="10:00", endtime="20:00") as context:
        # instance stopped outside period
        context.run_scheduling_request_handler(dt=quick_time(22, 0, 0))
        assert get_current_state(ec2_instance) == "stopped"

        # cx starts instance manually
        start_ec2_instances(ec2_instance)

        # instance is not stopped
        context.run_scheduling_request_handler(dt=quick_time(22, 5, 0))
        assert get_current_state(ec2_instance) == "running"


def test_instance_is_stopped_if_started_outside_running_period_when_schedule_is_enforced(
    ec2_instance: str,
    scheduling_context: SchedulingContext,
) -> None:
    stop_ec2_instances(ec2_instance)

    with simple_schedule(begintime="10:00", endtime="20:00", enforced=True) as context:
        # instance stopped outside period
        context.run_scheduling_request_handler(dt=quick_time(22, 0, 0))
        assert get_current_state(ec2_instance) == "stopped"

        # cx starts instance manually
        start_ec2_instances(ec2_instance)

        # instance is not stopped
        context.run_scheduling_request_handler(dt=quick_time(22, 5, 0))
        assert get_current_state(ec2_instance) == "stopped"


def test_multiple_ec2_instances_start_at_beginning_of_period(
    scheduling_context: SchedulingContext,
) -> None:
    from tests.integration.helpers.ec2_helpers import create_ec2_instances

    # create 2 instances with same schedule
    instance_ids = create_ec2_instances(2, "test-schedule")
    stop_ec2_instances(*instance_ids)

    with simple_schedule(begintime="10:00", endtime="20:00") as context:
        # before start of period
        context.run_scheduling_request_handler(dt=quick_time(9, 55))
        assert all(
            get_current_state(instance_id) == "stopped" for instance_id in instance_ids
        )
        # start of period - both instances should start
        context.run_scheduling_request_handler(dt=quick_time(10, 0))
        assert all(
            get_current_state(instance_id) == "running" for instance_id in instance_ids
        )


def test_events_sent_when_instance_started(
    ec2_instance: str,
    scheduling_context: SchedulingContext,
    mock_hub_events_client: MagicMock,
) -> None:
    stop_ec2_instances(ec2_instance)
    with simple_schedule(begintime="10:00", endtime="20:00") as context:
        context.run_scheduling_request_handler(dt=quick_time(10, 0))
        assert get_current_state(ec2_instance) == "running"

        # Extract events
        sent_events = extract_events(mock_hub_events_client)

        assert sent_events == UnorderedList(
            [
                {
                    "Source": "instance-scheduler",
                    "DetailType": "Scheduling Action",
                    "Resources": [
                        f"arn:aws:ec2:us-east-1:123456789012:instance/{ec2_instance}"
                    ],
                    "Detail": json.dumps(
                        {
                            "account": "123456789012",
                            "region": "us-east-1",
                            "service": "ec2",
                            "resource_id": ec2_instance,
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
                        f"arn:aws:ec2:us-east-1:123456789012:instance/{ec2_instance}"
                    ],
                    "Detail": json.dumps(
                        {
                            "account": "123456789012",
                            "region": "us-east-1",
                            "service": "ec2",
                            "resource_id": ec2_instance,
                            "requested_action": "Start",
                            "action_taken": "Started",
                            "schedule": "test-schedule",
                        }
                    ),
                    "EventBusName": "global-events",
                },
            ]
        )


def test_events_sent_when_instance_stopped(
    ec2_instance: str,
    scheduling_context: SchedulingContext,
    mock_hub_events_client: MagicMock,
) -> None:
    start_ec2_instances(ec2_instance)
    with simple_schedule(begintime="10:00", endtime="20:00") as context:
        context.run_scheduling_request_handler(dt=quick_time(20, 0))
        assert get_current_state(ec2_instance) == "stopped"

        # Extract events
        sent_events = extract_events(mock_hub_events_client)

        assert sent_events == UnorderedList(
            [
                {
                    "Source": "instance-scheduler",
                    "DetailType": "Scheduling Action",
                    "Resources": [
                        f"arn:aws:ec2:us-east-1:123456789012:instance/{ec2_instance}"
                    ],
                    "Detail": json.dumps(
                        {
                            "account": "123456789012",
                            "region": "us-east-1",
                            "service": "ec2",
                            "resource_id": ec2_instance,
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
                        f"arn:aws:ec2:us-east-1:123456789012:instance/{ec2_instance}"
                    ],
                    "Detail": json.dumps(
                        {
                            "account": "123456789012",
                            "region": "us-east-1",
                            "service": "ec2",
                            "resource_id": ec2_instance,
                            "requested_action": "Stop",
                            "action_taken": "Stopped",
                            "schedule": "test-schedule",
                        }
                    ),
                    "EventBusName": "global-events",
                },
            ]
        )
