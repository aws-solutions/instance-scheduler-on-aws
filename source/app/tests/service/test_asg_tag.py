# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import json
from datetime import datetime, timedelta, timezone
from typing import Final
from zoneinfo import ZoneInfo

from mypy_boto3_autoscaling.type_defs import AutoScalingGroupTypeDef
from pytest import fixture, raises

from instance_scheduler.model.period_definition import PeriodDefinition
from instance_scheduler.service.asg import (
    AsgSize,
    AsgTag,
    AsgTagValidationError,
    period_to_actions,
)

ASG_SCHEDULED_TAG_KEY: Final = "scheduled"
SCHEDULE_NAME: Final = "Schedule"


@fixture
def default_asg_group_definition() -> AutoScalingGroupTypeDef:
    return {
        "AutoScalingGroupName": "MockAutoScaling",
        "MinSize": 1,
        "MaxSize": 1,
        "DesiredCapacity": 1,
        "DefaultCooldown": 1,
        "AvailabilityZones": ["us-east-1a"],
        "HealthCheckType": "EC2",
        "CreatedTime": datetime(2024, 1, 1),
    }


def test_period_to_actions() -> None:
    name: Final = "SimplePeriod"
    tz: Final = ZoneInfo("Etc/UTC")
    size: Final = AsgSize(1, 1, 1)
    actions: Final = list(
        period_to_actions(
            PeriodDefinition(
                name=name,
                begintime="09:00",
                endtime="17:00",
                monthdays={"15"},
            ),
            tz,
            size,
            "is-",
        )
    )
    assert actions == [
        {
            "ScheduledActionName": f"is-{name}Start",
            "Recurrence": "0 9 15 * *",
            "MinSize": size.min_size,
            "MaxSize": size.max_size,
            "DesiredCapacity": size.desired_size,
            "TimeZone": str(tz),
        },
        {
            "ScheduledActionName": f"is-{name}Stop",
            "Recurrence": "0 17 15 * *",
            "MinSize": 0,
            "MaxSize": 0,
            "DesiredCapacity": 0,
            "TimeZone": str(tz),
        },
    ]


def test_asg_size_from_group(
    default_asg_group_definition: AutoScalingGroupTypeDef,
) -> None:
    # Call
    size = AsgSize.from_group(default_asg_group_definition)

    # Verify
    assert size.min_size == default_asg_group_definition.get("MinSize")
    assert size.max_size == default_asg_group_definition.get("MaxSize")
    assert size.desired_size == default_asg_group_definition.get("DesiredCapacity")


def test_asg_size_from_tag() -> None:
    # Prepare
    min_size = 1
    max_size = 3
    desired_size = 2
    tag_value = AsgTag(
        schedule="",
        ttl="",
        min_size=min_size,
        max_size=max_size,
        desired_size=desired_size,
    )

    # Call
    size = AsgSize.from_tag(tag_value)

    # Verify
    assert size.min_size == min_size
    assert size.max_size == max_size
    assert size.desired_size == desired_size


def test_asg_size_stopped() -> None:
    # Call
    size = AsgSize.stopped()

    # Verify
    assert size.is_stopped_state()


def test_asg_tag_from_group(
    default_asg_group_definition: AutoScalingGroupTypeDef,
) -> None:
    # Prepare
    group = default_asg_group_definition
    tag_value = AsgTag(
        schedule=SCHEDULE_NAME,
        ttl=(datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
        min_size=1,
        max_size=3,
        desired_size=2,
    )
    group["Tags"] = [{"Key": ASG_SCHEDULED_TAG_KEY, "Value": tag_value.to_json()}]

    # Call
    scheduled_tag_value = AsgTag.from_group(
        group=group, asg_scheduled_tag_key=ASG_SCHEDULED_TAG_KEY
    )

    # Verify
    assert scheduled_tag_value.schedule == tag_value.schedule
    assert scheduled_tag_value.ttl == tag_value.ttl
    assert scheduled_tag_value.min_size == tag_value.min_size
    assert scheduled_tag_value.max_size == tag_value.max_size
    assert scheduled_tag_value.desired_size == tag_value.desired_size


def test_asg_tag_from_group_when_no_scheduled_tag(
    default_asg_group_definition: AutoScalingGroupTypeDef,
) -> None:
    # Call
    with raises(AsgTagValidationError) as e:
        AsgTag.from_group(
            group=default_asg_group_definition,
            asg_scheduled_tag_key=ASG_SCHEDULED_TAG_KEY,
        )

    # Verify
    assert str(e.value) == "Scheduled tag missing"


def test_asg_tag_from_group_when_unable_to_parse(
    default_asg_group_definition: AutoScalingGroupTypeDef,
) -> None:
    # Prepare
    group = default_asg_group_definition
    group["Tags"] = [{"Key": ASG_SCHEDULED_TAG_KEY, "Value": "Mock"}]

    # Call
    with raises(AsgTagValidationError) as e:
        AsgTag.from_group(
            group=group,
            asg_scheduled_tag_key=ASG_SCHEDULED_TAG_KEY,
        )

    # Verify
    assert str(e.value) == "Unable to parse Scheduled tag value"


def test_asg_tag_from_group_when_scheduled_tag_invalid(
    default_asg_group_definition: AutoScalingGroupTypeDef,
) -> None:
    # Prepare
    group = default_asg_group_definition
    group["Tags"] = [{"Key": ASG_SCHEDULED_TAG_KEY, "Value": "1"}]

    # Call
    with raises(AsgTagValidationError) as e:
        AsgTag.from_group(
            group=group,
            asg_scheduled_tag_key=ASG_SCHEDULED_TAG_KEY,
        )

    # Verify
    assert str(e.value) == "Invalid Scheduled tag value: not a dict"


def test_asg_tag_not_valid_when_overridden() -> None:
    # Prepare
    ttl: Final = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
    asg_tag = AsgTag(
        schedule=SCHEDULE_NAME, ttl=ttl, min_size=1, max_size=3, desired_size=2
    )

    # Call
    valid, reason = asg_tag.is_still_valid(
        schedule_name=SCHEDULE_NAME,
        is_schedule_override=True,
    )

    # Verify
    assert not valid
    assert reason == "Overridden"


def test_asg_tag_not_valid_when_schedule_tag_schedule_different() -> None:
    # Prepare
    ttl: Final = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
    asg_tag = AsgTag(
        schedule=f"{SCHEDULE_NAME}Invalid",
        ttl=ttl,
        min_size=1,
        max_size=3,
        desired_size=2,
    )

    # Call
    valid, reason = asg_tag.is_still_valid(
        schedule_name=SCHEDULE_NAME,
        is_schedule_override=False,
    )

    # Verify
    assert not valid
    assert reason == "Configured for a different schedule"


def test_asg_tag_not_valid_when_schedule_tag_ttl_malformed() -> None:
    # Prepare
    asg_tag = AsgTag(
        schedule=SCHEDULE_NAME, ttl="", min_size=1, max_size=3, desired_size=2
    )

    # Call
    valid, reason = asg_tag.is_still_valid(
        schedule_name=SCHEDULE_NAME,
        is_schedule_override=False,
    )

    # Verify
    assert not valid
    assert reason == "Unable to parse configuration TTL"


def test_asg_tag_not_valid_when_schedule_tag_ttl_expired() -> None:
    # Prepare
    ttl: Final = datetime.now(timezone.utc).isoformat()
    asg_tag = AsgTag(
        schedule=SCHEDULE_NAME, ttl=ttl, min_size=1, max_size=3, desired_size=2
    )

    # Call
    valid, reason = asg_tag.is_still_valid(
        schedule_name=SCHEDULE_NAME,
        is_schedule_override=False,
    )

    # Verify
    assert not valid
    assert reason == "Configuration expiring in less than one day"


def test_asg_tag_is_still_valid() -> None:
    # Prepare
    ttl: Final = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
    asg_tag = AsgTag(
        schedule=SCHEDULE_NAME, ttl=ttl, min_size=1, max_size=3, desired_size=2
    )

    # Call
    valid, reason = asg_tag.is_still_valid(
        schedule_name=SCHEDULE_NAME,
        is_schedule_override=False,
    )

    # Verify
    assert valid
    assert (
        reason
        == f"All conditions met, current config valid for schedule {SCHEDULE_NAME} until {ttl}"
    )


def test_asg_tag_to_json() -> None:
    # Prepare
    ttl: Final = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
    asg_tag = AsgTag(
        schedule=SCHEDULE_NAME, ttl=ttl, min_size=1, max_size=3, desired_size=2
    )

    # Call
    json_str = asg_tag.to_json()

    # Verify
    assert json_str == json.dumps(
        {
            "schedule": asg_tag.schedule,
            "ttl": asg_tag.ttl,
            "min_size": asg_tag.min_size,
            "max_size": asg_tag.max_size,
            "desired_size": asg_tag.desired_size,
        }
    )
