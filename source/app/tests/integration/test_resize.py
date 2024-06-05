# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from mypy_boto3_ec2.literals import InstanceTypeType

from instance_scheduler.model.period_definition import PeriodDefinition
from instance_scheduler.schedulers.instance_states import InstanceStates
from tests.integration.helpers.ec2_helpers import (
    create_ec2_instances,
    get_current_instance_type,
    get_current_state,
    stop_ec2_instances,
)
from tests.integration.helpers.run_handler import resizable_multi_period_schedule
from tests.integration.helpers.schedule_helpers import quick_time


def test_stopped_instance_resized(
    ec2_instance: str,
    ec2_instance_states: InstanceStates,
) -> None:
    (ec2_instance,) = create_ec2_instances(
        1, "test-schedule", instance_type="c6g.medium"
    )
    desired_instance_type: InstanceTypeType = "c6g.2xlarge"

    stop_ec2_instances(ec2_instance)

    with resizable_multi_period_schedule(
        name="test-schedule",
        period_definitions=[
            {
                "period": PeriodDefinition(
                    name="test-period", begintime="10:00", endtime="20:00"
                ),
                "desired_type": desired_instance_type,
            }
        ],
    ) as context:
        # start and resize
        context.run_scheduling_request_handler(dt=quick_time(10, 0))
        assert get_current_state(ec2_instance) == "running"
        assert get_current_instance_type(ec2_instance) == desired_instance_type


def test_running_instance_is_stopped_for_resize(
    ec2_instance: str,
    ec2_instance_states: InstanceStates,
) -> None:
    (ec2_instance,) = create_ec2_instances(
        1, "test-schedule", instance_type="c6g.medium"
    )
    desired_instance_type: InstanceTypeType = "c6g.2xlarge"

    with resizable_multi_period_schedule(
        name="test-schedule",
        period_definitions=[
            {
                "period": PeriodDefinition(
                    name="test-period", begintime="10:00", endtime="20:00"
                ),
                "desired_type": desired_instance_type,
            }
        ],
    ) as context:
        # should stop instance so it can be resized
        context.run_scheduling_request_handler(dt=quick_time(15, 0))
        assert get_current_state(ec2_instance) == "stopped"

        # should restart instance as correct size
        context.run_scheduling_request_handler(dt=quick_time(15, 5))
        assert get_current_state(ec2_instance) == "running"
        assert get_current_instance_type(ec2_instance) == desired_instance_type


def test_resizing_with_multi_period_schedule(
    ec2_instance: str,
    ec2_instance_states: InstanceStates,
) -> None:
    (ec2_instance,) = create_ec2_instances(
        1, "test-schedule", instance_type="c6g.medium"
    )
    outer_period_instance_type: InstanceTypeType = "c6g.medium"
    inner_period_instance_type: InstanceTypeType = "c6g.2xlarge"

    with resizable_multi_period_schedule(
        name="test-schedule",
        period_definitions=[
            {
                "period": PeriodDefinition(
                    name="outer-period", begintime="5:00", endtime="20:00"
                ),
                "desired_type": outer_period_instance_type,
            },
            {
                "period": PeriodDefinition(
                    name="inner-period", begintime="12:00", endtime="14:00"
                ),
                "desired_type": inner_period_instance_type,
            },
        ],
    ) as context:
        # in outer period, no change should occur
        context.run_scheduling_request_handler(dt=quick_time(7, 0, 0))
        assert get_current_state(ec2_instance) == "running"
        assert get_current_instance_type(ec2_instance) == outer_period_instance_type

        # enter inner period, should resize
        context.run_scheduling_request_handler(dt=quick_time(12, 0, 0))
        assert get_current_state(ec2_instance) == "stopped"

        context.run_scheduling_request_handler(dt=quick_time(12, 5, 0))
        assert get_current_state(ec2_instance) == "running"
        assert get_current_instance_type(ec2_instance) == inner_period_instance_type

        # within inner period, no action (should not thrash with outer period)
        context.run_scheduling_request_handler(dt=quick_time(13, 0, 0))
        assert get_current_state(ec2_instance) == "running"
        assert get_current_instance_type(ec2_instance) == inner_period_instance_type

        # exit inner period, should resize to outer period
        context.run_scheduling_request_handler(dt=quick_time(14, 0, 0))
        assert get_current_state(ec2_instance) == "stopped"

        context.run_scheduling_request_handler(dt=quick_time(14, 5, 0))
        assert get_current_state(ec2_instance) == "running"
        assert get_current_instance_type(ec2_instance) == outer_period_instance_type
