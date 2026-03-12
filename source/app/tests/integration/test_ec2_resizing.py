# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from instance_scheduler.configuration.scheduling_context import SchedulingContext
from instance_scheduler.handler import resize_handler
from instance_scheduler.model.period_definition import PeriodDefinition
from mypy_boto3_ec2.literals import InstanceTypeType
from tests.integration.helpers.ec2_helpers import (
    create_ec2_instances,
    get_current_instance_type,
    get_current_state,
    stop_ec2_instances,
)
from tests.integration.helpers.run_handler import resizable_multi_period_schedule
from tests.integration.helpers.schedule_helpers import quick_time
from tests.integration.helpers.sqs_helpers import (
    mock_forward_sqs_messages_to_lambda_handler,
)
from tests.test_utils.mock_environs.mock_resize_environment import MockResizeEnvironment


def test_resize_on_instance_start(scheduling_context: SchedulingContext) -> None:
    (ec2_instance,) = create_ec2_instances(
        1, "test-schedule", instance_type="c6g.medium"
    )
    desired_instance_type: InstanceTypeType = "c6g.2xlarge"

    stop_ec2_instances(ec2_instance)

    with (
        mock_forward_sqs_messages_to_lambda_handler(
            lambda_handler=resize_handler.lambda_handler,
            lambda_env=MockResizeEnvironment(),
        ),
        resizable_multi_period_schedule(
            name="test-schedule",
            period_definitions=[
                {
                    "period": PeriodDefinition(
                        name="test-period", begintime="10:00", endtime="20:00"
                    ),
                    "desired_type": desired_instance_type,
                }
            ],
        ) as context,
    ):
        # start and resize
        context.run_scheduling_request_handler(dt=quick_time(10, 0))
        assert get_current_state(ec2_instance) == "running"
        assert get_current_instance_type(ec2_instance) == desired_instance_type


def test_running_instance_is_force_resized(
    scheduling_context: SchedulingContext,
) -> None:
    (ec2_instance,) = create_ec2_instances(
        1, "test-schedule", instance_type="c6g.medium"
    )
    desired_instance_type: InstanceTypeType = "c6g.2xlarge"

    with (
        mock_forward_sqs_messages_to_lambda_handler(
            lambda_handler=resize_handler.lambda_handler,
            lambda_env=MockResizeEnvironment(),
        ),
        resizable_multi_period_schedule(
            name="test-schedule",
            period_definitions=[
                {
                    "period": PeriodDefinition(
                        name="test-period", begintime="10:00", endtime="20:00"
                    ),
                    "desired_type": desired_instance_type,
                }
            ],
        ) as context,
    ):
        # should be stopped, resized, and restarted by resize-handler
        context.run_scheduling_request_handler(dt=quick_time(15, 0))
        assert get_current_state(ec2_instance) == "running"
        assert get_current_instance_type(ec2_instance) == desired_instance_type


def test_resizing_with_multi_period_schedule(
    scheduling_context: SchedulingContext,
) -> None:
    (ec2_instance,) = create_ec2_instances(
        1, "test-schedule", instance_type="c6g.medium"
    )
    outer_period_instance_type: InstanceTypeType = "c6g.medium"
    inner_period_instance_type: InstanceTypeType = "c6g.2xlarge"

    with (
        mock_forward_sqs_messages_to_lambda_handler(
            lambda_handler=resize_handler.lambda_handler,
            lambda_env=MockResizeEnvironment(),
        ),
        resizable_multi_period_schedule(
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
        ) as context,
    ):
        # in outer period, no change should occur
        context.run_scheduling_request_handler(dt=quick_time(7, 0, 0))
        assert get_current_state(ec2_instance) == "running"
        assert get_current_instance_type(ec2_instance) == outer_period_instance_type

        # enter inner period, should resize
        context.run_scheduling_request_handler(dt=quick_time(12, 5, 0))
        assert get_current_state(ec2_instance) == "running"
        assert get_current_instance_type(ec2_instance) == inner_period_instance_type

        # within inner period, no action (should not thrash with outer period)
        context.run_scheduling_request_handler(dt=quick_time(13, 0, 0))
        assert get_current_state(ec2_instance) == "running"
        assert get_current_instance_type(ec2_instance) == inner_period_instance_type

        # exit inner period, should resize to outer period
        context.run_scheduling_request_handler(dt=quick_time(14, 5, 0))
        assert get_current_state(ec2_instance) == "running"
        assert get_current_instance_type(ec2_instance) == outer_period_instance_type
