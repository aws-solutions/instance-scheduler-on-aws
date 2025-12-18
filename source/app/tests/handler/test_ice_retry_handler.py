# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from contextlib import contextmanager
from typing import Any, Iterator

from botocore.exceptions import ClientError
from instance_scheduler.configuration.scheduling_context import SchedulingContext
from instance_scheduler.handler.ice_retry_handler import (
    IceRetryRequestHandler,
    validate_ice_retry_request,
)
from instance_scheduler.scheduling.ec2 import Ec2Service
from instance_scheduler.scheduling.ec2.ice_retry import IceRetryRequest
from instance_scheduler.util.session_manager import AssumedRole
from instance_scheduler.util.validation import ValidationException
from pytest import raises
from tests.integration.helpers.boto_client_helpers import mock_specific_client
from tests.integration.helpers.ec2_helpers import (
    create_ec2_instances,
    get_current_state,
    stop_ec2_instances,
)
from tests.test_utils.mock_ice_retry_environment import MockIceRetryEnvironment


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
    role: AssumedRole, instance_type: str
) -> Iterator[None]:
    with mock_specific_client("ec2") as ec2_client:
        original_start_instances = ec2_client.start_instances

        def conditional_side_effect(*args: Any, **kwargs: Any) -> Any:
            instance_ids = kwargs.get("InstanceIds", args[0] if args else [])
            # Only raise error for specific instance type condition
            if instance_ids and instance_is_of_size(role, instance_ids, instance_type):
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


def ice_retry_request(
    instance_id: str,
    preferred_instance_types: list[str],
    account: str = "123456789012",  # moto defaults
    region: str = "us-east-1",
) -> IceRetryRequest:
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
        validate_ice_retry_request(invalid_request)


def test_ice_retry_handler_resizes_when_first_type_fails(
    scheduling_context: SchedulingContext,
) -> None:
    env = MockIceRetryEnvironment()

    ec2_instance = Ec2Service.describe_instance(
        scheduling_context.assumed_role,
        create_ec2_instances(1, "test_schedule", instance_type="t3.medium")[0],
    )

    if not ec2_instance:
        raise Exception("Error creating EC2 test instance")

    scheduling_context.registry.put(
        Ec2Service.fetch_or_create_registry_data(
            ec2_instance=ec2_instance,
            registry=scheduling_context.registry,
            schedule_tag_key=scheduling_context.schedule_tag_key,
        )
    )

    stop_ec2_instances()

    with ec2_client_will_raise_insufficient_capacity_error_for_size(
        scheduling_context.assumed_role, "t3.medium"
    ):
        handler = IceRetryRequestHandler(
            event={
                "account": scheduling_context.assumed_role.account,  # Use moto default account
                "region": scheduling_context.assumed_role.region,
                "instance_id": ec2_instance.resource_id,  # Use actual instance ID
                "preferred_instance_types": ["t3.medium", "t3.small"],
            },
            env=env,
            scheduling_context=scheduling_context,
        )
        result = handler.handle_request()

        assert result == "OK"
        assert get_current_state(ec2_instance.resource_id) == "running"
        assert instance_is_of_size(
            scheduling_context.assumed_role, [ec2_instance.resource_id], "t3.small"
        )


def test_ice_retry_handler_uses_first_type_if_possible(
    scheduling_context: SchedulingContext,
) -> None:
    env = MockIceRetryEnvironment()

    ec2_instance = Ec2Service.describe_instance(
        scheduling_context.assumed_role,
        create_ec2_instances(1, "test_schedule", instance_type="t3.small")[0],
    )

    if not ec2_instance:
        raise Exception("Error creating EC2 test instance")

    scheduling_context.registry.put(
        Ec2Service.fetch_or_create_registry_data(
            ec2_instance=ec2_instance,
            registry=scheduling_context.registry,
            schedule_tag_key=scheduling_context.schedule_tag_key,
        )
    )

    stop_ec2_instances()

    handler = IceRetryRequestHandler(
        event={
            "account": scheduling_context.assumed_role.account,  # Use moto default account
            "region": scheduling_context.assumed_role.region,
            "instance_id": ec2_instance.resource_id,  # Use actual instance ID
            "preferred_instance_types": ["t3.medium", "t3.small"],
        },
        env=env,
        scheduling_context=scheduling_context,
    )
    result = handler.handle_request()

    assert result == "OK"
    assert get_current_state(ec2_instance.resource_id) == "running"
    assert instance_is_of_size(
        scheduling_context.assumed_role, [ec2_instance.resource_id], "t3.medium"
    )
