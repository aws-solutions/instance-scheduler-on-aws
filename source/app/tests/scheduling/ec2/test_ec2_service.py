# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from typing import TYPE_CHECKING, Final

from instance_scheduler.model.managed_instance import RegisteredEc2Instance
from instance_scheduler.observability.tag_keys import ControlTagKey
from instance_scheduler.scheduling.ec2.ec2 import (
    EC2RuntimeInfo,
    Ec2Service,
    ManagedEC2Instance,
    get_tags,
)
from instance_scheduler.scheduling.scheduling_decision import (
    RequestedAction,
    SchedulingDecision,
)
from instance_scheduler.scheduling.scheduling_result import SchedulingAction
from instance_scheduler.scheduling.states import InstanceState
from instance_scheduler.util.arn import ARN
from tests.test_utils.mock_scheduling_request_environment import (
    MockSchedulingRequestEnvironment,
)

if TYPE_CHECKING:
    from mypy_boto3_ec2.type_defs import InstanceTypeDef
else:
    InstanceTypeDef = object


def test_get_tags() -> None:
    """Test the get_tags utility function."""
    assert get_tags({}) == {}

    instance: Final[InstanceTypeDef] = {
        "Tags": [
            {"Key": "foo", "Value": "bar"},
            {"Key": "baz", "Value": "qux"},
        ]
    }

    assert get_tags(instance) == {"foo": "bar", "baz": "qux"}


def test_get_tags_with_no_tags() -> None:
    """Test get_tags when instance has no Tags key."""
    instance: Final[InstanceTypeDef] = {}
    assert get_tags(instance) == {}


def test_get_tags_with_empty_tags() -> None:
    """Test get_tags when instance has empty Tags list."""
    instance: Final[InstanceTypeDef] = {"Tags": []}
    assert get_tags(instance) == {}


def test_hibernation_fallback_to_regular_stop() -> None:
    """Test hibernation fallback behavior when UnsupportedHibernationConfiguration occurs."""
    from unittest.mock import MagicMock

    from botocore.exceptions import ClientError

    # Mock EC2 client
    mock_ec2_client = MagicMock()

    # Configure hibernation to fail, then regular stop to succeed
    hibernation_error = ClientError(
        error_response={"Error": {"Code": "UnsupportedHibernationConfiguration"}},
        operation_name="StopInstances",
    )
    mock_ec2_client.stop_instances.side_effect = [
        hibernation_error,  # First call (hibernation) fails
        {
            "StoppingInstances": [{"InstanceId": "i-123"}]
        },  # Second call (regular stop) succeeds
    ]

    # Mock scheduling context
    mock_context = MagicMock()
    mock_context.hub_stack_name = "test-stack"
    mock_context.assumed_role.client.return_value = mock_ec2_client

    env = MockSchedulingRequestEnvironment()
    service = Ec2Service(mock_context, env)

    # Create test instance
    managed_instance = ManagedEC2Instance(
        registry_info=RegisteredEc2Instance(
            account="123456789012",
            region="us-east-1",
            resource_id="i-123",
            arn=ARN("arn:aws:ec2:us-east-1:123456789012:instance/i-123"),
            name="test-instance",
            schedule="test-schedule",
            stored_state=InstanceState.RUNNING,
        ),
        runtime_info=EC2RuntimeInfo(
            account="123456789012",
            region="us-east-1",
            resource_id="i-123",
            arn=ARN("arn:aws:ec2:us-east-1:123456789012:instance/i-123"),
            tags={"Name": "test-instance"},
            current_state="running",
            current_size="t3.micro",
        ),
    )

    # Create scheduling decision
    decision = SchedulingDecision(
        instance=managed_instance,
        action=RequestedAction.STOP,
        new_stored_state=InstanceState.STOPPED,
        reason="test stop",
    )

    # Test hibernation attempt that falls back to regular stop
    results = list(service.hibernate_instances([decision]))

    # Should call stop_instances twice: first hibernation (fails), then regular stop (succeeds)
    assert mock_ec2_client.stop_instances.call_count == 2

    # First call should be hibernation
    first_call_args = mock_ec2_client.stop_instances.call_args_list[0]
    assert first_call_args[1]["Hibernate"] is True
    assert first_call_args[1]["InstanceIds"] == ["i-123"]

    # Second call should be regular stop
    second_call_args = mock_ec2_client.stop_instances.call_args_list[1]
    assert second_call_args[1]["Hibernate"] is False
    assert second_call_args[1]["InstanceIds"] == ["i-123"]

    # Should return successful result with STOP action (fallback)
    assert len(results) == 1
    assert results[0].action_taken == SchedulingAction.STOP


def test_hibernation_with_schedule_hibernate_true() -> None:
    """Test that InstanceSchedule and ScheduleDefinition support hibernate field.

    This test verifies that hibernation configuration is properly supported
    in both InstanceSchedule and ScheduleDefinition classes.
    """
    from zoneinfo import ZoneInfo

    from instance_scheduler.configuration.instance_schedule import InstanceSchedule
    from instance_scheduler.model.schedule_definition import ScheduleDefinition

    # Test that InstanceSchedule supports hibernate field
    schedule_with_hibernation = InstanceSchedule(
        name="hibernate-schedule",
        timezone=ZoneInfo("UTC"),
        hibernate=True,  # This should trigger hibernation when implemented
    )

    # Verify the schedule has hibernation enabled
    assert schedule_with_hibernation.hibernate is True

    # Test schedule without hibernation
    schedule_without_hibernation = InstanceSchedule(
        name="regular-schedule",
        timezone=ZoneInfo("UTC"),
        hibernate=False,
    )

    assert schedule_without_hibernation.hibernate is False

    # Test that ScheduleDefinition also supports hibernate field
    schedule_def_with_hibernation = ScheduleDefinition(
        name="hibernate-schedule-def",
        hibernate=True,
        override_status="stopped",  # Required to make schedule valid
    )

    assert schedule_def_with_hibernation.hibernate is True

    # Test ScheduleDefinition without hibernation
    schedule_def_without_hibernation = ScheduleDefinition(
        name="regular-schedule-def",
        hibernate=False,
        override_status="running",  # Required to make schedule valid
    )

    assert schedule_def_without_hibernation.hibernate is False

    # Test ScheduleDefinition with None hibernation (default)
    schedule_def_default_hibernation = ScheduleDefinition(
        name="default-schedule-def",
        override_status="stopped",  # Required to make schedule valid
    )

    assert schedule_def_default_hibernation.hibernate is None


def test_hibernation_success() -> None:
    """Test successful hibernation flow."""
    from unittest.mock import MagicMock

    # Mock EC2 client
    mock_ec2_client = MagicMock()

    # Configure successful hibernation
    mock_ec2_client.stop_instances.return_value = {
        "StoppingInstances": [{"InstanceId": "i-123"}]
    }

    # Mock scheduling context
    mock_context = MagicMock()
    mock_context.hub_stack_name = "test-stack"
    mock_context.assumed_role.client.return_value = mock_ec2_client

    env = MockSchedulingRequestEnvironment()
    service = Ec2Service(mock_context, env)

    # Create test instance
    managed_instance = ManagedEC2Instance(
        registry_info=RegisteredEc2Instance(
            account="123456789012",
            region="us-east-1",
            resource_id="i-123",
            arn=ARN("arn:aws:ec2:us-east-1:123456789012:instance/i-123"),
            name="test-instance",
            schedule="test-schedule",
            stored_state=InstanceState.RUNNING,
        ),
        runtime_info=EC2RuntimeInfo(
            account="123456789012",
            region="us-east-1",
            resource_id="i-123",
            arn=ARN("arn:aws:ec2:us-east-1:123456789012:instance/i-123"),
            tags={"Name": "test-instance"},
            current_state="running",
            current_size="t3.micro",
        ),
    )

    # Create scheduling decision
    decision = SchedulingDecision(
        instance=managed_instance,
        action=RequestedAction.STOP,
        new_stored_state=InstanceState.STOPPED,
        reason="test hibernation",
    )

    # Test successful hibernation
    results = list(service.hibernate_instances([decision]))

    # Should call stop_instances once with hibernation
    assert mock_ec2_client.stop_instances.call_count == 1
    call_args = mock_ec2_client.stop_instances.call_args
    assert call_args[1]["Hibernate"] is True
    assert call_args[1]["InstanceIds"] == ["i-123"]

    # Should return successful result with HIBERNATE action
    assert len(results) == 1
    assert results[0].action_taken == SchedulingAction.HIBERNATE


def test_get_preferred_instance_types_with_tag() -> None:
    """Test _get_preferred_instance_types when preferred instance types tag is present."""

    # Create instance with alternate instance types tag
    managed_instance = ManagedEC2Instance(
        registry_info=RegisteredEc2Instance(
            account="123456789012",
            region="us-east-1",
            resource_id="i-123",
            arn=ARN("arn:aws:ec2:us-east-1:123456789012:instance/i-123"),
            name="test-instance",
            schedule="test-schedule",
            stored_state=InstanceState.RUNNING,
        ),
        runtime_info=EC2RuntimeInfo(
            account="123456789012",
            region="us-east-1",
            resource_id="i-123",
            arn=ARN("arn:aws:ec2:us-east-1:123456789012:instance/i-123"),
            tags={
                "Name": "test-instance",
                ControlTagKey.PREFERRED_INSTANCE_TYPES.value: "t3.small,t3.medium,t3.large",
            },
            current_state="running",
            current_size="t3.micro",
        ),
    )

    result = managed_instance.runtime_info.requested_instance_types
    assert result == ["t3.small", "t3.medium", "t3.large"]


def test_get_preferred_instance_types_without_tag() -> None:
    """Test _get_alternate_instance_types when alternate instance types tag is not present."""

    # Create instance without alternate instance types tag
    managed_instance = ManagedEC2Instance(
        registry_info=RegisteredEc2Instance(
            account="123456789012",
            region="us-east-1",
            resource_id="i-123",
            arn=ARN("arn:aws:ec2:us-east-1:123456789012:instance/i-123"),
            name="test-instance",
            schedule="test-schedule",
            stored_state=InstanceState.RUNNING,
        ),
        runtime_info=EC2RuntimeInfo(
            account="123456789012",
            region="us-east-1",
            resource_id="i-123",
            arn=ARN("arn:aws:ec2:us-east-1:123456789012:instance/i-123"),
            tags={"Name": "test-instance"},
            current_state="running",
            current_size="t3.micro",
        ),
    )

    result = managed_instance.runtime_info.requested_instance_types
    assert result == []


def test_get_preferred_instance_types_with_empty_tag() -> None:
    """Test _get_alternate_instance_types when alternate instance types tag is empty."""

    # Create instance with empty alternate instance types tag
    managed_instance = ManagedEC2Instance(
        registry_info=RegisteredEc2Instance(
            account="123456789012",
            region="us-east-1",
            resource_id="i-123",
            arn=ARN("arn:aws:ec2:us-east-1:123456789012:instance/i-123"),
            name="test-instance",
            schedule="test-schedule",
            stored_state=InstanceState.RUNNING,
        ),
        runtime_info=EC2RuntimeInfo(
            account="123456789012",
            region="us-east-1",
            resource_id="i-123",
            arn=ARN("arn:aws:ec2:us-east-1:123456789012:instance/i-123"),
            tags={
                "Name": "test-instance",
                ControlTagKey.PREFERRED_INSTANCE_TYPES.value: "",
            },
            current_state="running",
            current_size="t3.micro",
        ),
    )

    result = managed_instance.runtime_info.requested_instance_types
    assert result == []


def test_get_preferred_instance_types_single_type() -> None:
    """Test _get_alternate_instance_types with a single alternate instance type."""

    # Create instance with single alternate instance type
    managed_instance = ManagedEC2Instance(
        registry_info=RegisteredEc2Instance(
            account="123456789012",
            region="us-east-1",
            resource_id="i-123",
            arn=ARN("arn:aws:ec2:us-east-1:123456789012:instance/i-123"),
            name="test-instance",
            schedule="test-schedule",
            stored_state=InstanceState.RUNNING,
        ),
        runtime_info=EC2RuntimeInfo(
            account="123456789012",
            region="us-east-1",
            resource_id="i-123",
            arn=ARN("arn:aws:ec2:us-east-1:123456789012:instance/i-123"),
            tags={
                "Name": "test-instance",
                ControlTagKey.PREFERRED_INSTANCE_TYPES.value: "t3.small",
            },
            current_state="running",
            current_size="t3.micro",
        ),
    )

    result = managed_instance.runtime_info.requested_instance_types
    assert result == ["t3.small"]


def test_send_ice_retry_request_with_preferred_types() -> None:
    """Test _send_ice_retry_request sends message when alternate types exist and queue URL is set."""
    from unittest.mock import MagicMock, patch

    mock_context = MagicMock()
    mock_context.assumed_role.account = "123456789012"
    mock_context.assumed_role.region = "us-east-1"

    env = MockSchedulingRequestEnvironment(
        ice_retry_queue_url="https://sqs.us-east-1.amazonaws.com/123456789012/test-queue"
    )

    service = Ec2Service(mock_context, env)

    managed_instance = ManagedEC2Instance(
        registry_info=RegisteredEc2Instance(
            account="123456789012",
            region="us-east-1",
            resource_id="i-123",
            arn=ARN("arn:aws:ec2:us-east-1:123456789012:instance/i-123"),
            name="test-instance",
            schedule="test-schedule",
            stored_state=InstanceState.RUNNING,
        ),
        runtime_info=EC2RuntimeInfo(
            account="123456789012",
            region="us-east-1",
            resource_id="i-123",
            arn=ARN("arn:aws:ec2:us-east-1:123456789012:instance/i-123"),
            tags={
                ControlTagKey.PREFERRED_INSTANCE_TYPES.value: "t3.small,t3.medium",
            },
            current_state="stopped",
            current_size="t3.micro",
        ),
    )

    with patch(
        "instance_scheduler.scheduling.ec2.ec2.send_message_to_queue"
    ) as mock_send:
        mock_send.return_value = "message-id-123"

        service._send_ice_retry_request(
            SchedulingDecision(
                instance=managed_instance,
                action=RequestedAction.START,
                new_stored_state=InstanceState.RUNNING,
                reason="test start",
            )
        )

        mock_send.assert_called_once()
        call_args = mock_send.call_args
        assert (
            call_args[1]["queue_url"]
            == "https://sqs.us-east-1.amazonaws.com/123456789012/test-queue"
        )
        assert call_args[1]["delay_in_seconds"] == 10

        import json

        message_body = json.loads(call_args[1]["message_body"])
        assert message_body["account"] == "123456789012"
        assert message_body["region"] == "us-east-1"
        assert message_body["instance_id"] == "i-123"
        assert message_body["preferred_instance_types"] == ["t3.small", "t3.medium"]


def test_send_ice_retry_request_no_queue_url() -> None:
    """Test _send_ice_retry_request does nothing when queue URL is None."""
    from unittest.mock import MagicMock, patch

    mock_context = MagicMock()
    env = MockSchedulingRequestEnvironment(ice_retry_queue_url=None)

    service = Ec2Service(mock_context, env)

    managed_instance = ManagedEC2Instance(
        registry_info=RegisteredEc2Instance(
            account="123456789012",
            region="us-east-1",
            resource_id="i-123",
            arn=ARN("arn:aws:ec2:us-east-1:123456789012:instance/i-123"),
            name="test-instance",
            schedule="test-schedule",
            stored_state=InstanceState.RUNNING,
        ),
        runtime_info=EC2RuntimeInfo(
            account="123456789012",
            region="us-east-1",
            resource_id="i-123",
            arn=ARN("arn:aws:ec2:us-east-1:123456789012:instance/i-123"),
            tags={
                ControlTagKey.PREFERRED_INSTANCE_TYPES.value: "t3.small",
            },
            current_state="stopped",
            current_size="t3.micro",
        ),
    )

    with patch(
        "instance_scheduler.scheduling.ec2.ec2.send_message_to_queue"
    ) as mock_send:
        service._send_ice_retry_request(
            SchedulingDecision(
                instance=managed_instance,
                action=RequestedAction.START,
                new_stored_state=InstanceState.RUNNING,
                reason="test start",
            )
        )
        mock_send.assert_not_called()


def test_send_ice_retry_request_no_preferred_types() -> None:
    """Test _send_ice_retry_request does nothing when no alternate types exist."""
    from unittest.mock import MagicMock, patch

    mock_context = MagicMock()
    env = MockSchedulingRequestEnvironment(
        ice_retry_queue_url="https://sqs.us-east-1.amazonaws.com/123456789012/test-queue"
    )

    service = Ec2Service(mock_context, env)

    managed_instance = ManagedEC2Instance(
        registry_info=RegisteredEc2Instance(
            account="123456789012",
            region="us-east-1",
            resource_id="i-123",
            arn=ARN("arn:aws:ec2:us-east-1:123456789012:instance/i-123"),
            name="test-instance",
            schedule="test-schedule",
            stored_state=InstanceState.RUNNING,
        ),
        runtime_info=EC2RuntimeInfo(
            account="123456789012",
            region="us-east-1",
            resource_id="i-123",
            arn=ARN("arn:aws:ec2:us-east-1:123456789012:instance/i-123"),
            tags={"Name": "test-instance"},
            current_state="stopped",
            current_size="t3.micro",
        ),
    )

    with patch(
        "instance_scheduler.scheduling.ec2.ec2.send_message_to_queue"
    ) as mock_send:
        service._send_ice_retry_request(
            SchedulingDecision(
                instance=managed_instance,
                action=RequestedAction.START,
                new_stored_state=InstanceState.RUNNING,
                reason="test start",
            )
        )
        mock_send.assert_not_called()


def test_send_ice_retry_request_empty_preferred_types() -> None:
    """Test _send_ice_retry_request does nothing when alternate types tag is empty."""
    from unittest.mock import MagicMock, patch

    mock_context = MagicMock()
    env = MockSchedulingRequestEnvironment(
        ice_retry_queue_url="https://sqs.us-east-1.amazonaws.com/123456789012/test-queue"
    )

    service = Ec2Service(mock_context, env)

    managed_instance = ManagedEC2Instance(
        registry_info=RegisteredEc2Instance(
            account="123456789012",
            region="us-east-1",
            resource_id="i-123",
            arn=ARN("arn:aws:ec2:us-east-1:123456789012:instance/i-123"),
            name="test-instance",
            schedule="test-schedule",
            stored_state=InstanceState.RUNNING,
        ),
        runtime_info=EC2RuntimeInfo(
            account="123456789012",
            region="us-east-1",
            resource_id="i-123",
            arn=ARN("arn:aws:ec2:us-east-1:123456789012:instance/i-123"),
            tags={
                ControlTagKey.PREFERRED_INSTANCE_TYPES.value: "",
            },
            current_state="stopped",
            current_size="t3.micro",
        ),
    )

    with patch(
        "instance_scheduler.scheduling.ec2.ec2.send_message_to_queue"
    ) as mock_send:
        service._send_ice_retry_request(
            SchedulingDecision(
                instance=managed_instance,
                action=RequestedAction.START,
                new_stored_state=InstanceState.RUNNING,
                reason="test start",
            )
        )
        mock_send.assert_not_called()
