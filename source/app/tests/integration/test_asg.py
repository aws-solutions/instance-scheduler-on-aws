# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from collections.abc import Iterator
from dataclasses import replace
from datetime import datetime, time, timedelta, timezone
from os import environ
from typing import TYPE_CHECKING, Any, Final
from unittest.mock import MagicMock, patch
from uuid import UUID
from zoneinfo import ZoneInfo

from boto3 import client
from freezegun import freeze_time
from moto.core.models import DEFAULT_ACCOUNT_ID
from pytest import fixture, raises

from instance_scheduler.handler.asg import lambda_handler, schedule_auto_scaling_groups
from instance_scheduler.model.period_definition import PeriodDefinition
from instance_scheduler.model.store.dynamo_period_definition_store import (
    DynamoPeriodDefinitionStore,
)
from instance_scheduler.service.asg import AsgSize, AsgTag
from tests import DEFAULT_REGION
from tests.context import MockLambdaContext
from tests.integration.helpers.asg_helpers import (
    ASG_GROUP_NAME,
    ASG_SCHEDULED_TAG_KEY,
    RULE_PREFIX,
    SCHEDULE_TAG_KEY,
    TEST_DATETIME,
    ScheduleHelper,
    add_actions,
    build_lambda_event,
    create_asg,
    create_ecs_cluster_with_auto_scaling,
    create_simple_schedule,
    delete_all_actions,
    get_actions,
    get_scheduled_tag,
    get_tag_value,
    tag_group,
    verify_operational_metrics,
    verify_scheduled_actions_and_tagged,
)
from tests.test_utils.mock_asg_environment import MockAsgEnvironment
from tests.test_utils.mock_metrics_environment import MockMetricsEnviron

if TYPE_CHECKING:
    from mypy_boto3_autoscaling.client import AutoScalingClient
else:
    AutoScalingClient = object


@fixture
def schedule_a(config_table: str) -> Iterator[ScheduleHelper]:
    schedule_name: Final = "my-schedule"
    begin_hour: Final = 9
    end_hour: Final = 17
    time_zone: Final = ZoneInfo("America/New_York")
    create_simple_schedule(
        config_table_name=config_table,
        schedule_name=schedule_name,
        begin_time=time(hour=begin_hour),
        end_time=time(hour=end_hour),
        time_zone=time_zone,
    )

    yield ScheduleHelper(
        name=schedule_name,
        start_recurrence=f"0 {begin_hour} * * *",
        end_recurrence=f"0 {end_hour} * * *",
        time_zone=time_zone,
    )


@fixture
def schedule_b(config_table: str) -> Iterator[ScheduleHelper]:
    schedule_name: Final = "my-other-schedule"
    begin_hour: Final = 10
    end_hour: Final = 14
    time_zone: Final = ZoneInfo("Asia/Taipei")
    create_simple_schedule(
        config_table_name=config_table,
        schedule_name=schedule_name,
        begin_time=time(hour=begin_hour),
        end_time=time(hour=end_hour),
        time_zone=time_zone,
    )

    yield ScheduleHelper(
        name=schedule_name,
        start_recurrence=f"0 {begin_hour} * * *",
        end_recurrence=f"0 {end_hour} * * *",
        time_zone=time_zone,
    )


@fixture
def schedule_no_timezone(config_table: str) -> Iterator[ScheduleHelper]:
    schedule_name: Final = "my-no-tz-schedule"
    begin_hour: Final = 17
    end_hour: Final = 19
    create_simple_schedule(
        config_table_name=config_table,
        schedule_name=schedule_name,
        begin_time=time(hour=begin_hour),
        end_time=time(hour=end_hour),
    )

    yield ScheduleHelper(
        name=schedule_name,
        start_recurrence=f"0 {begin_hour} * * *",
        end_recurrence=f"0 {end_hour} * * *",
        time_zone=None,
    )


@fixture
def schedule_invalid(config_table: str) -> Iterator[ScheduleHelper]:
    schedule_name: Final = "my-invalid-schedule"
    begin_hour: Final = 0
    end_hour: Final = 5
    create_simple_schedule(
        config_table_name=config_table,
        schedule_name=schedule_name,
        begin_time=time(hour=begin_hour),
        end_time=time(hour=end_hour),
        monthdays={"15W"},
    )

    yield ScheduleHelper(
        name=schedule_name,
        start_recurrence="Not valid",
        end_recurrence="Not valid",
        time_zone=None,
    )


@patch("instance_scheduler.handler.asg.collect_metric")
def test_handler_without_schedule_names_should_send_operational_metrics_when_time(
    mock_collect_metric: MagicMock,
    schedule_a: ScheduleHelper,
) -> None:
    # Prepare
    running_size: Final = AsgSize(min_size=3, desired_size=5, max_size=20)
    create_asg(ASG_GROUP_NAME, running_size)
    tag_group(
        group_name=ASG_GROUP_NAME, tag_key=SCHEDULE_TAG_KEY, tag_value=schedule_a.name
    )
    event: Final[dict[str, Any]] = build_lambda_event(TEST_DATETIME, None)

    # Call
    with freeze_time(TEST_DATETIME):
        with MockAsgEnvironment():
            with MockMetricsEnviron(metrics_uuid=UUID(int=TEST_DATETIME.hour)):
                lambda_handler(event, MockLambdaContext())

    # Verify
    verify_scheduled_actions_and_tagged(
        asg_group_name=ASG_GROUP_NAME,
        schedule=schedule_a,
        asg_size=running_size,
        dt=TEST_DATETIME,
    )
    verify_operational_metrics(mock_collect_metric, True)


@patch("instance_scheduler.handler.asg.collect_metric")
def test_handler_without_schedule_names_should_not_send_operational_metrics_when_not_time(
    mock_collect_metric: MagicMock,
    schedule_a: ScheduleHelper,
) -> None:
    # Prepare
    running_size: Final = AsgSize(min_size=3, desired_size=5, max_size=20)
    create_asg(ASG_GROUP_NAME, running_size)
    tag_group(
        group_name=ASG_GROUP_NAME, tag_key=SCHEDULE_TAG_KEY, tag_value=schedule_a.name
    )
    event: Final[dict[str, Any]] = build_lambda_event(TEST_DATETIME, None)

    # Call
    with freeze_time(TEST_DATETIME):
        with MockAsgEnvironment():
            with MockMetricsEnviron(metrics_uuid=UUID(int=TEST_DATETIME.hour + 1)):
                lambda_handler(event, MockLambdaContext())

    # Verify
    verify_scheduled_actions_and_tagged(
        asg_group_name=ASG_GROUP_NAME,
        schedule=schedule_a,
        asg_size=running_size,
        dt=TEST_DATETIME,
    )
    verify_operational_metrics(mock_collect_metric, False)


@patch("instance_scheduler.handler.asg.collect_metric")
def test_handler_with_schedule_names_should_not_send_operational_metrics(
    mock_collect_metric: MagicMock,
    schedule_a: ScheduleHelper,
) -> None:
    # Prepare
    running_size: Final = AsgSize(min_size=3, desired_size=5, max_size=20)
    create_asg(ASG_GROUP_NAME, running_size)
    tag_group(
        group_name=ASG_GROUP_NAME, tag_key=SCHEDULE_TAG_KEY, tag_value=schedule_a.name
    )
    event: Final[dict[str, Any]] = build_lambda_event(TEST_DATETIME, ["my-schedule"])

    # Call
    with freeze_time(TEST_DATETIME):
        with MockAsgEnvironment():
            with MockMetricsEnviron(metrics_uuid=UUID(int=TEST_DATETIME.hour + 1)):
                lambda_handler(event, MockLambdaContext())

    # Verify
    verify_scheduled_actions_and_tagged(
        asg_group_name=ASG_GROUP_NAME,
        schedule=schedule_a,
        asg_size=running_size,
        dt=TEST_DATETIME,
    )
    verify_operational_metrics(mock_collect_metric, False)


def test_asg_configured_with_schedule(
    config_table: str,
    schedule_a: ScheduleHelper,
) -> None:
    # Prepare
    running_size: Final = AsgSize(min_size=3, desired_size=5, max_size=20)
    create_asg(ASG_GROUP_NAME, running_size)
    tag_group(
        group_name=ASG_GROUP_NAME, tag_key=SCHEDULE_TAG_KEY, tag_value=schedule_a.name
    )

    # Call
    with freeze_time(TEST_DATETIME):
        schedule_auto_scaling_groups(
            schedule_tag_key=SCHEDULE_TAG_KEY,
            config_table_name=config_table,
            account_id=DEFAULT_ACCOUNT_ID,
            region=DEFAULT_REGION,
            scheduling_role_name="my-role",
            asg_scheduled_tag_key=ASG_SCHEDULED_TAG_KEY,
            rule_prefix=RULE_PREFIX,
            schedule_names=None,
        )

    # Verify
    verify_scheduled_actions_and_tagged(
        asg_group_name=ASG_GROUP_NAME,
        schedule=schedule_a,
        asg_size=running_size,
        dt=TEST_DATETIME,
    )


def test_asg_with_other_tag_not_configured(
    config_table: str, schedule_a: ScheduleHelper
) -> None:
    # Prepare
    running_size: Final = AsgSize(min_size=3, desired_size=5, max_size=20)
    create_asg(ASG_GROUP_NAME, running_size)
    tag_group(
        group_name=ASG_GROUP_NAME, tag_key="SomethingElse", tag_value=schedule_a.name
    )

    # Call
    schedule_auto_scaling_groups(
        schedule_tag_key=SCHEDULE_TAG_KEY,
        config_table_name=config_table,
        account_id=DEFAULT_ACCOUNT_ID,
        region=DEFAULT_REGION,
        scheduling_role_name="my-role",
        asg_scheduled_tag_key=ASG_SCHEDULED_TAG_KEY,
        rule_prefix=RULE_PREFIX,
        schedule_names=None,
    )

    # Verify
    assert len(list(get_actions(ASG_GROUP_NAME))) == 0

    with raises(KeyError):
        get_tag_value(group_name=ASG_GROUP_NAME, tag_key=ASG_SCHEDULED_TAG_KEY)


def test_asg_not_reconfigured_if_tag_remains(
    config_table: str, schedule_a: ScheduleHelper
) -> None:
    # Prepare
    running_size: Final = AsgSize(min_size=3, desired_size=5, max_size=20)
    create_asg(ASG_GROUP_NAME, running_size)
    tag_group(
        group_name=ASG_GROUP_NAME, tag_key=SCHEDULE_TAG_KEY, tag_value=schedule_a.name
    )

    # Call
    with freeze_time(TEST_DATETIME):
        schedule_auto_scaling_groups(
            schedule_tag_key=SCHEDULE_TAG_KEY,
            config_table_name=config_table,
            account_id=DEFAULT_ACCOUNT_ID,
            region=DEFAULT_REGION,
            scheduling_role_name="my-role",
            asg_scheduled_tag_key=ASG_SCHEDULED_TAG_KEY,
            rule_prefix=RULE_PREFIX,
            schedule_names=None,
        )

    # Verify
    verify_scheduled_actions_and_tagged(
        asg_group_name=ASG_GROUP_NAME,
        schedule=schedule_a,
        asg_size=running_size,
        dt=TEST_DATETIME,
    )

    # Prepare
    delete_all_actions(ASG_GROUP_NAME)

    # Call
    with freeze_time(TEST_DATETIME + timedelta(days=1)):
        schedule_auto_scaling_groups(
            schedule_tag_key=SCHEDULE_TAG_KEY,
            config_table_name=config_table,
            account_id=DEFAULT_ACCOUNT_ID,
            region=DEFAULT_REGION,
            scheduling_role_name="my-role",
            asg_scheduled_tag_key=ASG_SCHEDULED_TAG_KEY,
            rule_prefix=RULE_PREFIX,
            schedule_names=None,
        )

    # Verify
    assert len(list(get_actions(ASG_GROUP_NAME))) == 0

    new_tag: Final[AsgTag] = get_scheduled_tag(ASG_GROUP_NAME)
    assert new_tag == AsgTag(
        schedule=schedule_a.name,
        ttl=(TEST_DATETIME + timedelta(days=30)).isoformat(),
        min_size=running_size.min_size,
        max_size=running_size.max_size,
        desired_size=running_size.desired_size,
    )


def test_asg_reconfigured_if_tag_removed(
    config_table: str, schedule_a: ScheduleHelper
) -> None:
    # Prepare
    running_size: Final = AsgSize(min_size=3, desired_size=5, max_size=20)
    create_asg(ASG_GROUP_NAME, running_size)
    tag_group(
        group_name=ASG_GROUP_NAME, tag_key=SCHEDULE_TAG_KEY, tag_value=schedule_a.name
    )

    # Call
    with freeze_time(TEST_DATETIME):
        schedule_auto_scaling_groups(
            schedule_tag_key=SCHEDULE_TAG_KEY,
            config_table_name=config_table,
            account_id=DEFAULT_ACCOUNT_ID,
            region=DEFAULT_REGION,
            scheduling_role_name="my-role",
            asg_scheduled_tag_key=ASG_SCHEDULED_TAG_KEY,
            rule_prefix=RULE_PREFIX,
            schedule_names=None,
        )

    # Verify
    verify_scheduled_actions_and_tagged(
        asg_group_name=ASG_GROUP_NAME,
        schedule=schedule_a,
        asg_size=running_size,
        dt=TEST_DATETIME,
    )

    # Prepare
    delete_all_actions(ASG_GROUP_NAME)

    autoscaling: Final[AutoScalingClient] = client("autoscaling")
    autoscaling.delete_tags(
        Tags=[
            {
                "Key": ASG_SCHEDULED_TAG_KEY,
                "ResourceId": ASG_GROUP_NAME,
                "ResourceType": "auto-scaling-group",
            }
        ]
    )
    new_dt: Final = TEST_DATETIME + timedelta(days=1)

    # Call
    with freeze_time(new_dt):
        schedule_auto_scaling_groups(
            schedule_tag_key=SCHEDULE_TAG_KEY,
            config_table_name=config_table,
            account_id=DEFAULT_ACCOUNT_ID,
            region=DEFAULT_REGION,
            scheduling_role_name="my-role",
            asg_scheduled_tag_key=ASG_SCHEDULED_TAG_KEY,
            rule_prefix=RULE_PREFIX,
            schedule_names=None,
        )

    # Verify
    verify_scheduled_actions_and_tagged(
        asg_group_name=ASG_GROUP_NAME,
        schedule=schedule_a,
        asg_size=running_size,
        dt=new_dt,
    )


def test_asg_reconfigured_if_schedule_changed(
    config_table: str,
    schedule_a: ScheduleHelper,
    schedule_b: ScheduleHelper,
) -> None:
    # Prepare
    running_size: Final = AsgSize(min_size=3, desired_size=5, max_size=20)
    create_asg(ASG_GROUP_NAME, running_size)
    tag_group(
        group_name=ASG_GROUP_NAME, tag_key=SCHEDULE_TAG_KEY, tag_value=schedule_a.name
    )

    # Call
    with freeze_time(TEST_DATETIME):
        schedule_auto_scaling_groups(
            schedule_tag_key=SCHEDULE_TAG_KEY,
            config_table_name=config_table,
            account_id=DEFAULT_ACCOUNT_ID,
            region=DEFAULT_REGION,
            scheduling_role_name="my-role",
            asg_scheduled_tag_key=ASG_SCHEDULED_TAG_KEY,
            rule_prefix=RULE_PREFIX,
            schedule_names=None,
        )

    # Verify
    verify_scheduled_actions_and_tagged(
        asg_group_name=ASG_GROUP_NAME,
        schedule=schedule_a,
        asg_size=running_size,
        dt=TEST_DATETIME,
    )

    # Prepare
    tag_group(
        group_name=ASG_GROUP_NAME, tag_key=SCHEDULE_TAG_KEY, tag_value=schedule_b.name
    )
    new_dt: Final = TEST_DATETIME + timedelta(days=1)

    # Call
    with freeze_time(new_dt):
        schedule_auto_scaling_groups(
            schedule_tag_key=SCHEDULE_TAG_KEY,
            config_table_name=config_table,
            account_id=DEFAULT_ACCOUNT_ID,
            region=DEFAULT_REGION,
            scheduling_role_name="my-role",
            asg_scheduled_tag_key=ASG_SCHEDULED_TAG_KEY,
            rule_prefix=RULE_PREFIX,
            schedule_names=None,
        )

    # Verify
    verify_scheduled_actions_and_tagged(
        asg_group_name=ASG_GROUP_NAME,
        schedule=schedule_b,
        asg_size=running_size,
        dt=new_dt,
    )
    assert len(list(get_actions(ASG_GROUP_NAME))) == 2


def test_asg_reconfigured_if_tag_expired(
    config_table: str, schedule_a: ScheduleHelper
) -> None:
    # Prepare
    running_size: Final = AsgSize(min_size=3, desired_size=5, max_size=20)
    create_asg(ASG_GROUP_NAME, running_size)
    tag_group(
        group_name=ASG_GROUP_NAME, tag_key=SCHEDULE_TAG_KEY, tag_value=schedule_a.name
    )

    # Call
    with freeze_time(TEST_DATETIME):
        schedule_auto_scaling_groups(
            schedule_tag_key=SCHEDULE_TAG_KEY,
            config_table_name=config_table,
            account_id=DEFAULT_ACCOUNT_ID,
            region=DEFAULT_REGION,
            scheduling_role_name="my-role",
            asg_scheduled_tag_key=ASG_SCHEDULED_TAG_KEY,
            rule_prefix=RULE_PREFIX,
            schedule_names=None,
        )

    # Verify
    verify_scheduled_actions_and_tagged(
        asg_group_name=ASG_GROUP_NAME,
        schedule=schedule_a,
        asg_size=running_size,
        dt=TEST_DATETIME,
    )

    # Prepare
    delete_all_actions(ASG_GROUP_NAME)
    new_dt: Final = TEST_DATETIME + timedelta(days=31)

    # Call
    with freeze_time(new_dt):
        schedule_auto_scaling_groups(
            schedule_tag_key=SCHEDULE_TAG_KEY,
            config_table_name=config_table,
            account_id=DEFAULT_ACCOUNT_ID,
            region=DEFAULT_REGION,
            scheduling_role_name="my-role",
            asg_scheduled_tag_key=ASG_SCHEDULED_TAG_KEY,
            rule_prefix=RULE_PREFIX,
            schedule_names=None,
        )

    # Verify
    verify_scheduled_actions_and_tagged(
        asg_group_name=ASG_GROUP_NAME,
        schedule=schedule_a,
        asg_size=running_size,
        dt=new_dt,
    )


def test_stopped_asg_not_configured(
    config_table: str, schedule_a: ScheduleHelper
) -> None:
    # Prepare
    running_size: Final = AsgSize.stopped()
    create_asg(ASG_GROUP_NAME, running_size)
    tag_group(
        group_name=ASG_GROUP_NAME, tag_key=SCHEDULE_TAG_KEY, tag_value=schedule_a.name
    )

    # Call
    with freeze_time(TEST_DATETIME):
        schedule_auto_scaling_groups(
            schedule_tag_key=SCHEDULE_TAG_KEY,
            config_table_name=config_table,
            account_id=DEFAULT_ACCOUNT_ID,
            region=DEFAULT_REGION,
            scheduling_role_name="my-role",
            asg_scheduled_tag_key=ASG_SCHEDULED_TAG_KEY,
            rule_prefix=RULE_PREFIX,
            schedule_names=None,
        )

    # Verify
    assert len(list(get_actions(ASG_GROUP_NAME))) == 0

    with raises(KeyError):
        get_scheduled_tag(ASG_GROUP_NAME)


def test_asg_configured_with_default_timezone_if_not_specified(
    config_table: str,
    schedule_no_timezone: ScheduleHelper,
) -> None:
    # Prepare
    running_size: Final = AsgSize(min_size=3, desired_size=5, max_size=20)
    create_asg(ASG_GROUP_NAME, running_size)
    tag_group(
        group_name=ASG_GROUP_NAME,
        tag_key=SCHEDULE_TAG_KEY,
        tag_value=schedule_no_timezone.name,
    )
    expected_tz: Final = ZoneInfo("Europe/Helsinki")

    # Call
    with freeze_time(TEST_DATETIME), patch.dict(
        environ, {"DEFAULT_TIMEZONE": str(expected_tz)}
    ):
        schedule_auto_scaling_groups(
            schedule_tag_key=SCHEDULE_TAG_KEY,
            config_table_name=config_table,
            account_id=DEFAULT_ACCOUNT_ID,
            region=DEFAULT_REGION,
            scheduling_role_name="my-role",
            asg_scheduled_tag_key=ASG_SCHEDULED_TAG_KEY,
            rule_prefix=RULE_PREFIX,
            schedule_names=None,
        )

    # Verify
    expected_schedule: Final = replace(schedule_no_timezone, time_zone=expected_tz)
    verify_scheduled_actions_and_tagged(
        asg_group_name=ASG_GROUP_NAME,
        schedule=expected_schedule,
        asg_size=running_size,
        dt=TEST_DATETIME,
    )


def test_asg_not_configured_if_schedule_invalid(
    config_table: str, schedule_invalid: ScheduleHelper
) -> None:
    # Prepare
    running_size: Final = AsgSize(min_size=3, desired_size=5, max_size=20)
    create_asg(ASG_GROUP_NAME, running_size)
    tag_group(
        group_name=ASG_GROUP_NAME,
        tag_key=SCHEDULE_TAG_KEY,
        tag_value=schedule_invalid.name,
    )

    # Call
    schedule_auto_scaling_groups(
        schedule_tag_key=SCHEDULE_TAG_KEY,
        config_table_name=config_table,
        account_id=DEFAULT_ACCOUNT_ID,
        region=DEFAULT_REGION,
        scheduling_role_name="my-role",
        asg_scheduled_tag_key=ASG_SCHEDULED_TAG_KEY,
        rule_prefix=RULE_PREFIX,
        schedule_names=None,
    )

    # Verify
    assert len(list(get_actions(ASG_GROUP_NAME))) == 0

    with raises(KeyError):
        get_tag_value(group_name=ASG_GROUP_NAME, tag_key=ASG_SCHEDULED_TAG_KEY)


def test_preexisting_rules_not_removed(
    config_table: str, schedule_a: ScheduleHelper
) -> None:
    # Prepare
    running_size: Final = AsgSize(min_size=3, desired_size=5, max_size=20)
    create_asg(ASG_GROUP_NAME, running_size)
    tag_group(
        group_name=ASG_GROUP_NAME, tag_key=SCHEDULE_TAG_KEY, tag_value=schedule_a.name
    )

    action_name: Final = "my-action"
    autoscaling: Final[AutoScalingClient] = client("autoscaling")
    autoscaling.put_scheduled_update_group_action(
        AutoScalingGroupName=ASG_GROUP_NAME,
        ScheduledActionName=action_name,
        MinSize=1,
        DesiredCapacity=2,
        MaxSize=3,
        StartTime=datetime(year=2024, month=3, day=1, tzinfo=timezone.utc),
    )

    # Call
    with freeze_time(TEST_DATETIME):
        schedule_auto_scaling_groups(
            schedule_tag_key=SCHEDULE_TAG_KEY,
            config_table_name=config_table,
            account_id=DEFAULT_ACCOUNT_ID,
            region=DEFAULT_REGION,
            scheduling_role_name="my-role",
            asg_scheduled_tag_key=ASG_SCHEDULED_TAG_KEY,
            rule_prefix=RULE_PREFIX,
            schedule_names=None,
        )

    # Verify
    verify_scheduled_actions_and_tagged(
        asg_group_name=ASG_GROUP_NAME,
        schedule=schedule_a,
        asg_size=running_size,
        dt=TEST_DATETIME,
    )

    actions: Final = list(get_actions(ASG_GROUP_NAME))
    assert len(actions) == 3
    assert (
        len(
            list(
                filter(
                    lambda action: action["ScheduledActionName"] == action_name, actions
                )
            )
        )
        == 1
    )


def test_asg_reconfigured_if_schedule_name_specified(
    config_table: str, schedule_a: ScheduleHelper
) -> None:
    # Prepare
    running_size: Final = AsgSize(min_size=3, desired_size=5, max_size=20)
    create_asg(ASG_GROUP_NAME, running_size)
    tag_group(
        group_name=ASG_GROUP_NAME, tag_key=SCHEDULE_TAG_KEY, tag_value=schedule_a.name
    )

    # Call
    with freeze_time(TEST_DATETIME):
        schedule_auto_scaling_groups(
            schedule_tag_key=SCHEDULE_TAG_KEY,
            config_table_name=config_table,
            account_id=DEFAULT_ACCOUNT_ID,
            region=DEFAULT_REGION,
            scheduling_role_name="my-role",
            asg_scheduled_tag_key=ASG_SCHEDULED_TAG_KEY,
            rule_prefix=RULE_PREFIX,
            schedule_names=None,
        )

    # Verify
    verify_scheduled_actions_and_tagged(
        asg_group_name=ASG_GROUP_NAME,
        schedule=schedule_a,
        asg_size=running_size,
        dt=TEST_DATETIME,
    )

    # Prepare
    period_store: Final = DynamoPeriodDefinitionStore(table_name=config_table)
    begin_hour: Final = 20
    end_hour: Final = 22
    begin_time: Final = time(hour=begin_hour)
    end_time: Final = time(hour=22)
    period_name: Final = f"{schedule_a.name}-period"
    period: Final = PeriodDefinition(
        name=period_name,
        begintime=begin_time.strftime("%H:%M"),
        endtime=end_time.strftime("%H:%M"),
    )
    period_store.put(period, overwrite=True)

    schedule_a_updated: Final = replace(
        schedule_a,
        start_recurrence=f"0 {begin_hour} * * *",
        end_recurrence=f"0 {end_hour} * * *",
    )
    new_dt: Final = TEST_DATETIME + timedelta(days=1)

    # Call
    with freeze_time(new_dt):
        schedule_auto_scaling_groups(
            schedule_tag_key=SCHEDULE_TAG_KEY,
            config_table_name=config_table,
            account_id=DEFAULT_ACCOUNT_ID,
            region=DEFAULT_REGION,
            scheduling_role_name="my-role",
            asg_scheduled_tag_key=ASG_SCHEDULED_TAG_KEY,
            rule_prefix=RULE_PREFIX,
            schedule_names=[schedule_a_updated.name],
        )

    # Verify
    verify_scheduled_actions_and_tagged(
        asg_group_name=ASG_GROUP_NAME,
        schedule=schedule_a_updated,
        asg_size=running_size,
        dt=new_dt,
    )
    assert len(list(get_actions(ASG_GROUP_NAME))) == 2


def test_update_schedule_when_schedule_tag_value_is_updated(
    config_table: str,
    schedule_a: ScheduleHelper,
    schedule_b: ScheduleHelper,
) -> None:
    """
    Scenario:
    An auto scaling group is scheduled and tagged with `schedule_a` and `initial_tag_size` initially.
    Then, a user updates the auto scaling group tag to `schedule_b` and update the schedules.
    The new schedule should be based on the current auto scaling size, `running_size` and `schedule_b`.
    """

    # Prepare
    initial_tag_size: Final = AsgSize(min_size=1, desired_size=2, max_size=3)
    running_size: Final = AsgSize(min_size=3, desired_size=5, max_size=20)
    create_asg(ASG_GROUP_NAME, running_size)
    tag_group(
        group_name=ASG_GROUP_NAME, tag_key=SCHEDULE_TAG_KEY, tag_value=schedule_b.name
    )
    tag_group(
        group_name=ASG_GROUP_NAME,
        tag_key=ASG_SCHEDULED_TAG_KEY,
        tag_value=AsgTag(
            schedule=schedule_a.name,
            ttl=(TEST_DATETIME + timedelta(days=30)).isoformat(),
            min_size=initial_tag_size.min_size,
            max_size=initial_tag_size.max_size,
            desired_size=initial_tag_size.desired_size,
        ).to_json(),
    )
    add_actions(
        group_name=ASG_GROUP_NAME, asg_size=initial_tag_size, schedule=schedule_a
    )

    # Initial verification for the preparation
    verify_scheduled_actions_and_tagged(
        asg_group_name=ASG_GROUP_NAME,
        schedule=schedule_a,
        asg_size=initial_tag_size,
        dt=TEST_DATETIME,
    )

    # Call
    with freeze_time(TEST_DATETIME):
        schedule_auto_scaling_groups(
            schedule_tag_key=SCHEDULE_TAG_KEY,
            config_table_name=config_table,
            account_id=DEFAULT_ACCOUNT_ID,
            region=DEFAULT_REGION,
            scheduling_role_name="my-role",
            asg_scheduled_tag_key=ASG_SCHEDULED_TAG_KEY,
            rule_prefix=RULE_PREFIX,
            schedule_names=None,
        )

    # Verify
    verify_scheduled_actions_and_tagged(
        asg_group_name=ASG_GROUP_NAME,
        schedule=schedule_b,
        asg_size=running_size,
        dt=TEST_DATETIME,
    )


def test_update_schedule_when_tag_is_updated_and_asg_stopped(
    config_table: str,
    schedule_a: ScheduleHelper,
    schedule_b: ScheduleHelper,
) -> None:
    """
    Scenario:
    An auto scaling group is scheduled and tagged with `schedule_a` and `initial_tag_size` initially.
    Then, a user updates the auto scaling group tag to `schedule_b` and update the schedules.
    However, as the auto scaling group is currently stopped,
    the new schedule should be based on the existing tag size, `initial_tag_size`, and `schedule_b`.
    """

    # Prepare
    initial_tag_size: Final = AsgSize(min_size=1, desired_size=2, max_size=3)
    create_asg(ASG_GROUP_NAME, AsgSize.stopped())
    tag_group(
        group_name=ASG_GROUP_NAME, tag_key=SCHEDULE_TAG_KEY, tag_value=schedule_b.name
    )
    tag_group(
        group_name=ASG_GROUP_NAME,
        tag_key=ASG_SCHEDULED_TAG_KEY,
        tag_value=AsgTag(
            schedule=schedule_a.name,
            ttl=(TEST_DATETIME + timedelta(days=30)).isoformat(),
            min_size=initial_tag_size.min_size,
            max_size=initial_tag_size.max_size,
            desired_size=initial_tag_size.desired_size,
        ).to_json(),
    )
    add_actions(
        group_name=ASG_GROUP_NAME, asg_size=initial_tag_size, schedule=schedule_a
    )

    # Initial verification for the preparation
    verify_scheduled_actions_and_tagged(
        asg_group_name=ASG_GROUP_NAME,
        schedule=schedule_a,
        asg_size=initial_tag_size,
        dt=TEST_DATETIME,
    )

    # Call
    with freeze_time(TEST_DATETIME):
        schedule_auto_scaling_groups(
            schedule_tag_key=SCHEDULE_TAG_KEY,
            config_table_name=config_table,
            account_id=DEFAULT_ACCOUNT_ID,
            region=DEFAULT_REGION,
            scheduling_role_name="my-role",
            asg_scheduled_tag_key=ASG_SCHEDULED_TAG_KEY,
            rule_prefix=RULE_PREFIX,
            schedule_names=None,
        )

    # Verify
    verify_scheduled_actions_and_tagged(
        asg_group_name=ASG_GROUP_NAME,
        schedule=schedule_b,
        asg_size=initial_tag_size,
        dt=TEST_DATETIME,
    )


def test_schedule_ecs_autoscaling_group(
    config_table: str, schedule_a: ScheduleHelper
) -> None:
    # Prepare
    ecs_asg_group_name: Final = "ecs-asg"
    running_size: Final = AsgSize(min_size=1, max_size=10, desired_size=5)
    create_ecs_cluster_with_auto_scaling(
        ecs_asg_group_name=ecs_asg_group_name, running_size=running_size
    )
    tag_group(
        group_name=ecs_asg_group_name,
        tag_key=SCHEDULE_TAG_KEY,
        tag_value=schedule_a.name,
    )

    # Call
    with freeze_time(TEST_DATETIME):
        schedule_auto_scaling_groups(
            schedule_tag_key=SCHEDULE_TAG_KEY,
            config_table_name=config_table,
            account_id=DEFAULT_ACCOUNT_ID,
            region=DEFAULT_REGION,
            scheduling_role_name="my-role",
            asg_scheduled_tag_key=ASG_SCHEDULED_TAG_KEY,
            rule_prefix=RULE_PREFIX,
            schedule_names=None,
        )

    # Verify
    verify_scheduled_actions_and_tagged(
        asg_group_name=ecs_asg_group_name,
        schedule=schedule_a,
        asg_size=running_size,
        dt=TEST_DATETIME,
    )


# - configure fails, rules are rolled back (???), existing rules are left in place
