# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for the resource registration handler.

Focused on ASG CloudTrail tagging events. The ``AsgTag`` model previously
required ``value`` and ``propagateAtLaunch``, but CloudTrail only includes the
fields the caller actually sent: ``CreateOrUpdateTags`` may omit
``PropagateAtLaunch`` and ``DeleteTags`` sends neither. Those payloads raised
``ValidationError`` and aborted registration. These tests pin the tolerant
parsing and the register/deregister dispatch behavior.
"""

from contextlib import ExitStack
from typing import Any, Iterator
from unittest.mock import MagicMock, patch

from pytest import fixture
from tests.test_utils.mock_environs.mock_resource_registration_environment import (
    MockResourceRegistrationEnvironment,
)

# The handler instantiates its environment and registry at import time, so the
# environment must be present before the module is imported.
with MockResourceRegistrationEnvironment().patch_env(clear=False):
    from instance_scheduler.handler import resource_registration_handler as handler

HANDLER = "instance_scheduler.handler.resource_registration_handler"


def _asg_event(
    *tags: dict[str, Any], event_name: str = "CreateOrUpdateTags"
) -> dict[str, Any]:
    return {
        "source": "aws.autoscaling",
        "account": "111122223333",
        "region": "us-east-1",
        "detail": {
            "eventSource": "autoscaling.amazonaws.com",
            "eventName": event_name,
            "requestParameters": {"tags": list(tags)},
        },
    }


def test_create_or_update_tags_without_propagate_at_launch_parses() -> None:
    """The most common CLI/SDK/IaC tagging call omits PropagateAtLaunch."""
    event = _asg_event(
        {
            "resourceId": "my-asg",
            "resourceType": "auto-scaling-group",
            "key": "Schedule",
            "value": "office-hours",
        }
    )

    parsed = handler.AsgRegistrationEvent(**event)

    tag = parsed.detail.requestParameters.tags[0]
    assert tag.value == "office-hours"
    assert tag.propagateAtLaunch is None


def test_delete_tags_without_value_or_propagate_parses() -> None:
    """DeleteTags sends neither value nor propagateAtLaunch."""
    event = _asg_event(
        {
            "resourceId": "my-asg",
            "resourceType": "auto-scaling-group",
            "key": "Schedule",
        },
        event_name="DeleteTags",
    )

    parsed = handler.AsgRegistrationEvent(**event)

    tag = parsed.detail.requestParameters.tags[0]
    assert tag.value is None
    assert tag.propagateAtLaunch is None


def test_full_payload_parses() -> None:
    """The console sends the complete payload; it must still parse."""
    event = _asg_event(
        {
            "resourceId": "my-asg",
            "resourceType": "auto-scaling-group",
            "key": "Schedule",
            "value": "office-hours",
            "propagateAtLaunch": True,
        }
    )

    parsed = handler.AsgRegistrationEvent(**event)

    tag = parsed.detail.requestParameters.tags[0]
    assert tag.value == "office-hours"
    assert tag.propagateAtLaunch is True


@fixture
def patched_dispatch() -> Iterator[dict[str, MagicMock]]:
    """Patch the handler's external dependencies for dispatch tests."""
    targets = {
        "assume_role": "assume_role",
        "describe_asgs": "AsgService.describe_asgs",
        "register": "register_asg_resources",
        "deregister": "deregister_asg_resources",
        "registry": "registry",
        "from_arn": "RegistryKey.from_arn",
    }
    with ExitStack() as stack:
        mocks = {
            name: stack.enter_context(patch(f"{HANDLER}.{target}"))
            for name, target in targets.items()
        }
        mocks["assume_role"].return_value = MagicMock()
        mocks["from_arn"].return_value = MagicMock()
        yield mocks


def test_registers_when_schedule_tag_present(
    patched_dispatch: dict[str, MagicMock],
) -> None:
    """A create/update whose live describe shows the schedule tag registers."""
    described = MagicMock(tags={"Schedule": "office-hours"}, arn=MagicMock())
    patched_dispatch["describe_asgs"].return_value = iter([described])

    event = handler.AsgRegistrationEvent(
        **_asg_event(
            {
                "resourceId": "my-asg",
                "resourceType": "auto-scaling-group",
                "key": "Schedule",
                "value": "office-hours",
            }
        )
    )

    result = handler.handle_asg_tagging_event(event)

    assert result["statusCode"] == 200
    patched_dispatch["register"].assert_called_once()
    patched_dispatch["deregister"].assert_not_called()


def test_deregisters_when_schedule_tag_absent(
    patched_dispatch: dict[str, MagicMock],
) -> None:
    """A delete whose live describe shows no schedule tag deregisters."""
    described = MagicMock(tags={}, arn=MagicMock())
    patched_dispatch["describe_asgs"].return_value = iter([described])
    patched_dispatch["registry"].get.return_value = MagicMock()

    event = handler.AsgRegistrationEvent(
        **_asg_event(
            {
                "resourceId": "my-asg",
                "resourceType": "auto-scaling-group",
                "key": "Schedule",
            },
            event_name="DeleteTags",
        )
    )

    result = handler.handle_asg_tagging_event(event)

    assert result["statusCode"] == 200
    patched_dispatch["deregister"].assert_called_once()
    patched_dispatch["register"].assert_not_called()


def test_delete_event_with_no_registry_record_is_noop(
    patched_dispatch: dict[str, MagicMock],
) -> None:
    """A delete event for an ASG with no registry record is a safe no-op.

    Exercises the false branch of the ``if registry_record:`` guard: the ASG was
    already deregistered (or never registered), so there is nothing to remove and
    deregister_asg_resources must not be called. This is the delete/create race the
    handler defends against, and this change is what first activates the DeleteTags
    path in production.
    """
    described = MagicMock(tags={}, arn=MagicMock())
    patched_dispatch["describe_asgs"].return_value = iter([described])
    patched_dispatch["registry"].get.return_value = None

    event = handler.AsgRegistrationEvent(
        **_asg_event(
            {
                "resourceId": "my-asg",
                "resourceType": "auto-scaling-group",
                "key": "Schedule",
            },
            event_name="DeleteTags",
        )
    )

    result = handler.handle_asg_tagging_event(event)

    assert result["statusCode"] == 200
    patched_dispatch["deregister"].assert_not_called()


def test_ignores_non_schedule_tag_keys(
    patched_dispatch: dict[str, MagicMock],
) -> None:
    """Events for unrelated tag keys do not describe, register, or deregister."""
    event = handler.AsgRegistrationEvent(
        **_asg_event(
            {
                "resourceId": "my-asg",
                "resourceType": "auto-scaling-group",
                "key": "SomeOtherTag",
                "value": "x",
            }
        )
    )

    result = handler.handle_asg_tagging_event(event)

    assert result["statusCode"] == 200
    patched_dispatch["describe_asgs"].assert_not_called()
    patched_dispatch["register"].assert_not_called()
    patched_dispatch["deregister"].assert_not_called()


def test_tag_update_delete_then_create_resolves_to_registered(
    patched_dispatch: dict[str, MagicMock],
) -> None:
    """A tag-value update arrives as a DeleteTags event immediately followed by a
    CreateOrUpdateTags event. Before the optional-fields fix, the DeleteTags half
    failed to parse and aborted before the describe-based reconciliation. This test
    verifies both halves now parse and, because a value update leaves the tag key
    present, the live describe shows it throughout, so each half registers and the
    ASG stays registered. It does not exercise the tag-absent ordering; the false
    branch is covered by test_deregisters_when_schedule_tag_absent and
    test_delete_event_with_no_registry_record_is_noop.
    """
    described = MagicMock(tags={"Schedule": "office-hours"}, arn=MagicMock())
    patched_dispatch["describe_asgs"].side_effect = lambda *a, **k: iter([described])

    delete_half = handler.AsgRegistrationEvent(
        **_asg_event(
            {
                "resourceId": "my-asg",
                "resourceType": "auto-scaling-group",
                "key": "Schedule",
            },
            event_name="DeleteTags",
        )
    )
    create_half = handler.AsgRegistrationEvent(
        **_asg_event(
            {
                "resourceId": "my-asg",
                "resourceType": "auto-scaling-group",
                "key": "Schedule",
                "value": "office-hours",
            }
        )
    )

    # Both halves parse and are processed; neither raises.
    handler.handle_asg_tagging_event(delete_half)
    handler.handle_asg_tagging_event(create_half)

    # The live describe shows the schedule tag present, so both halves register and
    # the ASG is never deregistered (correct final state: registered).
    assert patched_dispatch["register"].call_count == 2
    patched_dispatch["deregister"].assert_not_called()


def _create_asg_event(asg_name: str, *tags: dict[str, Any]) -> dict[str, Any]:
    """Build a CreateAutoScalingGroup CloudTrail event.

    The group name is carried in requestParameters.autoScalingGroupName and the tag
    entries may omit resourceId/resourceType (unlike CreateOrUpdateTags/DeleteTags).
    """
    return {
        "source": "aws.autoscaling",
        "account": "111122223333",
        "region": "us-east-1",
        "detail": {
            "eventSource": "autoscaling.amazonaws.com",
            "eventName": "CreateAutoScalingGroup",
            "requestParameters": {
                "autoScalingGroupName": asg_name,
                "tags": list(tags),
            },
        },
    }


def test_create_auto_scaling_group_payload_parses() -> None:
    """A group created with the schedule tag emits CreateAutoScalingGroup, whose
    tag entries carry no resourceId and whose group name is separate."""
    parsed = handler.AsgRegistrationEvent(
        **_create_asg_event(
            "my-asg",
            {"key": "Schedule", "value": "office-hours"},
        )
    )

    assert parsed.detail.requestParameters.autoScalingGroupName == "my-asg"
    tag = parsed.detail.requestParameters.tags[0]
    assert tag.key == "Schedule"
    assert tag.resourceId is None
    assert tag.resourceType is None


def test_create_auto_scaling_group_registers(
    patched_dispatch: dict[str, MagicMock],
) -> None:
    """A CreateAutoScalingGroup event registers the group named in
    requestParameters.autoScalingGroupName when its live tags include the schedule
    tag. This is the created-with-tag case that emits no CreateOrUpdateTags event.
    """
    described = MagicMock(tags={"Schedule": "office-hours"}, arn=MagicMock())
    patched_dispatch["describe_asgs"].return_value = iter([described])

    event = handler.AsgRegistrationEvent(
        **_create_asg_event(
            "my-asg",
            {"key": "Schedule", "value": "office-hours"},
        )
    )

    result = handler.handle_asg_tagging_event(event)

    assert result["statusCode"] == 200
    patched_dispatch["describe_asgs"].assert_called_once_with(
        patched_dispatch["assume_role"].return_value, ["my-asg"]
    )
    patched_dispatch["register"].assert_called_once()
    patched_dispatch["deregister"].assert_not_called()


def test_create_auto_scaling_group_without_group_name_is_noop(
    patched_dispatch: dict[str, MagicMock],
) -> None:
    """A malformed CreateAutoScalingGroup event lacking autoScalingGroupName does
    nothing rather than raising."""
    event_dict: dict[str, Any] = {
        "source": "aws.autoscaling",
        "account": "111122223333",
        "region": "us-east-1",
        "detail": {
            "eventSource": "autoscaling.amazonaws.com",
            "eventName": "CreateAutoScalingGroup",
            "requestParameters": {
                "tags": [{"key": "Schedule", "value": "office-hours"}],
            },
        },
    }
    event = handler.AsgRegistrationEvent(**event_dict)

    result = handler.handle_asg_tagging_event(event)

    assert result["statusCode"] == 200
    patched_dispatch["describe_asgs"].assert_not_called()
    patched_dispatch["register"].assert_not_called()
    patched_dispatch["deregister"].assert_not_called()


def test_create_auto_scaling_group_without_schedule_tag_is_noop(
    patched_dispatch: dict[str, MagicMock],
) -> None:
    """If the live describe of a just-created group does not show the schedule tag,
    the shared reconcile takes the else branch: with no registry record it neither
    registers nor deregisters. Verifies the "safe even if described without the
    tag" behavior for the create path.
    """
    described = MagicMock(tags={}, arn=MagicMock())
    patched_dispatch["describe_asgs"].return_value = iter([described])
    patched_dispatch["registry"].get.return_value = None  # never registered

    event = handler.AsgRegistrationEvent(
        **_create_asg_event("my-asg", {"key": "Schedule"})
    )

    result = handler.handle_asg_tagging_event(event)

    assert result["statusCode"] == 200
    patched_dispatch["register"].assert_not_called()
    patched_dispatch["deregister"].assert_not_called()
