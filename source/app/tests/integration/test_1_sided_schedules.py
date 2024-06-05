# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import datetime

from instance_scheduler.configuration.running_period import RunningPeriod
from instance_scheduler.configuration.running_period_dict_element import (
    RunningPeriodDictElement,
)
from instance_scheduler.schedulers.instance_states import InstanceStates
from tests.integration.helpers.ec2_helpers import (
    create_ec2_instances,
    get_current_state,
    stop_ec2_instances,
)
from tests.integration.helpers.run_handler import simple_schedule
from tests.integration.helpers.schedule_helpers import quick_time

one_sided_start = RunningPeriodDictElement(
    period=RunningPeriod(name="one-sided-start", begintime=datetime.time(10, 0, 0))
)

one_sided_stop = RunningPeriodDictElement(
    period=RunningPeriod(name="one-sided-stop", endtime=datetime.time(20, 0, 0))
)


def test_enforced_1_sided_start_takes_no_action_before_start_time(
    ec2_instance_states: InstanceStates,
) -> None:
    running_instance, stopped_instance = create_ec2_instances(
        count=2, schedule_name="test-schedule"
    )
    stop_ec2_instances(stopped_instance)

    with simple_schedule(
        name="test-schedule", begintime="10:00", enforced=True
    ) as context:
        # first contact (populates state table)
        context.run_scheduling_request_handler(dt=quick_time(9, 50))
        assert get_current_state(stopped_instance) == "stopped"
        assert get_current_state(running_instance) == "running"

        # second contact
        context.run_scheduling_request_handler(dt=quick_time(9, 55))
        assert get_current_state(stopped_instance) == "stopped"
        assert get_current_state(running_instance) == "running"


def test_enforced_1_sided_stop_takes_no_action_before_stop_time(
    ec2_instance_states: InstanceStates,
) -> None:
    running_instance, stopped_instance = create_ec2_instances(
        count=2, schedule_name="test-schedule"
    )
    stop_ec2_instances(stopped_instance)

    with simple_schedule(
        name="test-schedule", endtime="20:00", enforced=True
    ) as context:
        # first contact (populates state table)
        context.run_scheduling_request_handler(dt=quick_time(9, 50))
        assert get_current_state(stopped_instance) == "stopped"
        assert get_current_state(running_instance) == "running"

        # second contact
        context.run_scheduling_request_handler(dt=quick_time(9, 55))
        assert get_current_state(stopped_instance) == "stopped"
        assert get_current_state(running_instance) == "running"


def test_1_sided_stop_stops_at_stop_time(
    ec2_instance: str,
    ec2_instance_states: InstanceStates,
) -> None:
    with simple_schedule(endtime="20:00") as context:
        # before stop (populates state table)
        context.run_scheduling_request_handler(dt=quick_time(19, 55))
        assert get_current_state(ec2_instance) == "running"

        # at stop
        context.run_scheduling_request_handler(dt=quick_time(20, 0))
        assert get_current_state(ec2_instance) == "stopped"


def test_1_sided_start_starts_at_start_time(
    ec2_instance: str,
    ec2_instance_states: InstanceStates,
) -> None:
    stop_ec2_instances(ec2_instance)
    with simple_schedule(begintime="10:00") as context:
        # before start (populates state table)
        context.run_scheduling_request_handler(dt=quick_time(9, 55))
        assert get_current_state(ec2_instance) == "stopped"

        # at stop
        context.run_scheduling_request_handler(dt=quick_time(10, 0))
        assert get_current_state(ec2_instance) == "running"
