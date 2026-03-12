# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from contextlib import contextmanager
from typing import Any, Iterator

from botocore.exceptions import ClientError
from instance_scheduler.configuration.scheduling_context import SchedulingContext
from instance_scheduler.handler import resize_handler
from instance_scheduler.handler.environments.resize_request_environment import (
    Ec2ResizeRequest,
)
from instance_scheduler.handler.resize_handler import (
    validate_resize_request,
)
from instance_scheduler.scheduling.ec2 import Ec2Service
from instance_scheduler.util.session_manager import AssumedRole, lambda_execution_role
from instance_scheduler.util.validation import ValidationException
from mypy_boto3_ec2.client import EC2Client
from pytest import raises
from tests.integration.helpers.boto_client_helpers import mock_specific_client
from tests.integration.helpers.ec2_helpers import (
    create_ec2_instances,
    get_current_instance_type,
    get_current_state,
    stop_ec2_instances,
)
from tests.integration.helpers.run_handler import simple_schedule
from tests.integration.helpers.schedule_helpers import quick_time
from tests.integration.helpers.sqs_helpers import (
    mock_forward_sqs_messages_to_lambda_handler,
)
from tests.test_utils.mock_environs.mock_resize_environment import MockResizeEnvironment


def instance_is_of_size(
    role: AssumedRole, instance_ids: list[str], target_instance_type: str
) -> bool:
    for instance_id in instance_ids:
        runtime_info = Ec2Service.describe_instance(role, instance_id)

        if runtime_info and runtime_info.current_size == target_instance_type:
            return True

    return False


@contextmanager
def ec2_client_will_raise_insufficient_capacity_error_for_size(
    role: AssumedRole, *instance_types: str
) -> Iterator[None]:
    with mock_specific_client("ec2") as ec2_client:
        original_start_instances = ec2_client.start_instances

        def conditional_side_effect(*args: Any, **kwargs: Any) -> Any:
            instance_ids = kwargs.get("InstanceIds", args[0] if args else [])
            for instance_id in instance_ids:
                for blocked_type in instance_types:
                    if instance_is_of_size(role, [instance_id], blocked_type):
                        print(f"raising error for start of size: {blocked_type}")
                        raise ClientError(
                            {
                                "Error": {
                                    "Code": "InsufficientInstanceCapacity",
                                    "Message": "Insufficient capacity",
                                }
                            },
                            "StartInstances",
                        )
            # Call the original method without side_effect to avoid recursion
            ec2_client.start_instances.side_effect = None
            result = original_start_instances(*args, **kwargs)
            ec2_client.start_instances.side_effect = conditional_side_effect
            return result

        ec2_client.start_instances.side_effect = conditional_side_effect
        try:
            yield
        finally:
            ec2_client.start_instances.side_effect = None


def resize_request(
    instance_id: str,
    preferred_instance_types: list[str],
    account: str = "123456789012",  # moto defaults
    region: str = "us-east-1",
) -> Ec2ResizeRequest:
    return {
        "account": account,
        "region": region,
        "instance_id": instance_id,
        "preferred_instance_types": preferred_instance_types,
    }


def test_validate_ice_retry_request_missing_required_field() -> None:
    invalid_request = {
        "account": "111111111111",
        "region": "us-east-1",
        # missing instance_id
        "preferred_instance_types": ["t3.small"],
    }
    with raises(ValidationException):
        validate_resize_request(invalid_request)


def test_ice_error_test_helper_raises_error_in_correct_scenarios(
    scheduling_context: SchedulingContext,
) -> None:
    with ec2_client_will_raise_insufficient_capacity_error_for_size(
        lambda_execution_role(), "t3.medium", "t3.small"
    ):
        will_raise1 = create_ec2_instances(
            1, "test_schedule", instance_type="t3.small"
        )[0]
        will_raise2 = create_ec2_instances(
            1, "test_schedule", instance_type="t3.medium"
        )[0]
        wont_raise = create_ec2_instances(1, "test_schedule", instance_type="t3.large")[
            0
        ]

        ec2_client: EC2Client = lambda_execution_role().client("ec2")

        with raises(ClientError) as exc_info1:
            ec2_client.start_instances(InstanceIds=[will_raise1])
        assert (
            exc_info1.value.response["Error"]["Code"] == "InsufficientInstanceCapacity"
        )

        with raises(ClientError) as exc_info2:
            ec2_client.start_instances(InstanceIds=[will_raise2])
        assert (
            exc_info2.value.response["Error"]["Code"] == "InsufficientInstanceCapacity"
        )

        ec2_client.start_instances(InstanceIds=[wont_raise])


def test_ICE_results_in_resizing_to_alternative_type(
    scheduling_context: SchedulingContext,
) -> None:
    (ec2_instance,) = create_ec2_instances(
        1,
        "test-schedule",
        instance_type="t3.medium",
        additional_tags=[
            {"Key": "IS-PreferredInstanceTypes", "Value": "t3.medium,t3.large,t3xlarge"}
        ],
    )

    stop_ec2_instances(ec2_instance)

    with (
        mock_forward_sqs_messages_to_lambda_handler(
            lambda_handler=resize_handler.lambda_handler,
            lambda_env=MockResizeEnvironment(),
        ),
        ec2_client_will_raise_insufficient_capacity_error_for_size(
            lambda_execution_role(), "t3.medium"
        ),
        simple_schedule(begintime="10:00", endtime="20:00") as context,
    ):
        # start and resize
        context.run_scheduling_request_handler(dt=quick_time(10, 0))
        assert get_current_state(ec2_instance) == "running"
        assert (
            get_current_instance_type(ec2_instance) == "t3.large"
        )  # resized from medium to large


def test_multiple_ICE_results_in_resizing_to_tertiary_type(
    scheduling_context: SchedulingContext,
) -> None:
    (ec2_instance,) = create_ec2_instances(
        1,
        "test-schedule",
        instance_type="t3.medium",
        additional_tags=[
            {
                "Key": "IS-PreferredInstanceTypes",
                "Value": "t3.medium,t3.large,t3.xlarge",
            }
        ],
    )

    stop_ec2_instances(ec2_instance)

    with (
        mock_forward_sqs_messages_to_lambda_handler(
            lambda_handler=resize_handler.lambda_handler,
            lambda_env=MockResizeEnvironment(),
        ),
        ec2_client_will_raise_insufficient_capacity_error_for_size(
            lambda_execution_role(), "t3.medium", "t3.large"
        ),
        simple_schedule(begintime="10:00", endtime="20:00") as context,
    ):
        # start and resize
        context.run_scheduling_request_handler(dt=quick_time(10, 0))
        assert get_current_state(ec2_instance) == "running"
        assert (
            get_current_instance_type(ec2_instance) == "t3.xlarge"
        )  # resized from medium to large


def test_resizes_to_most_preferred_type_on_next_possible_start_results(
    scheduling_context: SchedulingContext,
) -> None:
    (ec2_instance,) = create_ec2_instances(
        1,
        "test-schedule",
        instance_type="t3.medium",
        additional_tags=[
            {"Key": "IS-PreferredInstanceTypes", "Value": "t3.medium,t3.large,t3xlarge"}
        ],
    )

    stop_ec2_instances(ec2_instance)

    # ICE incident causes resize
    with (
        mock_forward_sqs_messages_to_lambda_handler(
            lambda_handler=resize_handler.lambda_handler,
            lambda_env=MockResizeEnvironment(),
        ),
        ec2_client_will_raise_insufficient_capacity_error_for_size(
            lambda_execution_role(), "t3.medium"
        ),
        simple_schedule(begintime="10:00", endtime="20:00") as context,
    ):
        # start and resize
        context.run_scheduling_request_handler(dt=quick_time(10, 0))
        assert get_current_state(ec2_instance) == "running"
        assert (
            get_current_instance_type(ec2_instance) == "t3.large"
        )  # resized from medium to large

    with (
        mock_forward_sqs_messages_to_lambda_handler(
            lambda_handler=resize_handler.lambda_handler,
            lambda_env=MockResizeEnvironment(),
        ),
        # no more ICE error in conditions
        simple_schedule(begintime="10:00", endtime="20:00") as context,
    ):
        # is not resized back during current period
        context.run_scheduling_request_handler(dt=quick_time(15, 0))
        assert get_current_state(ec2_instance) == "running"
        assert get_current_instance_type(ec2_instance) == "t3.large"

        # stops normally at end of period
        context.run_scheduling_request_handler(dt=quick_time(20, 0))
        assert get_current_state(ec2_instance) == "stopped"
        assert get_current_instance_type(ec2_instance) == "t3.large"

        # reszied at start of next period
        context.run_scheduling_request_handler(dt=quick_time(10, 0))
        assert get_current_state(ec2_instance) == "running"
        assert get_current_instance_type(ec2_instance) == "t3.medium"
