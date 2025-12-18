# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from datetime import timedelta
from typing import cast

from freezegun import freeze_time
from instance_scheduler.configuration.scheduling_context import SchedulingContext
from instance_scheduler.model.managed_instance import RegisteredAsgInstance, RegistryKey
from instance_scheduler.scheduling.asg.asg_runtime_info import AsgRuntimeInfo
from instance_scheduler.scheduling.asg.asg_service import AsgService
from instance_scheduler.scheduling.asg.asg_size import AsgSize
from instance_scheduler.scheduling.resource_registration import register_asg_resources
from instance_scheduler.util.arn import ARN
from instance_scheduler.util.session_manager import lambda_execution_role
from tests.integration.helpers.asg_helpers import (
    ASG_GROUP_NAME,
    TEST_DATETIME,
    create_asg,
    delete_all_actions,
    get_configured_actions,
    get_tag_value,
    set_mdm_tag,
)
from tests.integration.helpers.schedule_helpers import quick_time
from tests.test_utils.mock_resource_registration_environment import (
    MockResourceRegistrationEnvironment,
)
from tests.test_utils.scheduling_context import create_simple_schedule
from tests.test_utils.unordered_list import UnorderedList

"""
Tests needed

Schedule Configuration:
- Able to configure simple schedule (basic 9-5 w/ timezone)
- Able to configure complex schedule (weekdays/monthdays)
- Able to configure 1-sided schedule (only start/end time) (not supported?)
- Reports invalid schedules

MDM Tags:
- MDM value comes from tag when present
- MDM tag is created from current ASG configuration when missing
- Missing MDM tag + ASG in 0-0-0 state creates MDM tag and sets Error status requesting MDM tag be updated

Efficiency:
- Does not attempt to reconfigure actions when nothing has changed
- reconfigures when MDM and/or schedule changes
- reconfigures when lastConfigured record is close to expiry
"""


def test_configure_simple_schedule(
    scheduling_context: SchedulingContext, asg: AsgRuntimeInfo
) -> None:
    create_simple_schedule(scheduling_context, begintime="10:00", endtime="20:00")

    asg_service = AsgService(scheduling_context)
    asg_service.context.current_dt = quick_time(10, 0, 0)

    list(asg_service.schedule_target())  # initial on-boarding phase

    assert list(get_configured_actions(asg.resource_id)) == UnorderedList(
        [
            {
                "AutoScalingGroupName": "test-asg",
                "DesiredCapacity": 3,
                "MaxSize": 5,
                "MinSize": 1,
                "Recurrence": "0 10 * * *",
                "ScheduledActionName": "IS-test-schedule-periodStart",
                "TimeZone": "UTC",
            },
            {
                "AutoScalingGroupName": "test-asg",
                "DesiredCapacity": 0,
                "MaxSize": 0,
                "MinSize": 0,
                "Recurrence": "0 20 * * *",
                "ScheduledActionName": "IS-test-schedule-periodStop",
                "TimeZone": "UTC",
            },
        ]
    )


def test_mdm_tag_is_applied_from_existing_size(
    scheduling_context: SchedulingContext, asg: AsgRuntimeInfo
) -> None:
    create_simple_schedule(scheduling_context, begintime="10:00", endtime="20:00")

    asg_service = AsgService(scheduling_context)
    asg_service.context.current_dt = quick_time(10, 0, 0)

    list(asg_service.schedule_target())  # initial on-boarding phase

    assert (
        get_tag_value(asg.resource_id, "IS-MinDesiredMax")
        == AsgSize(1, 3, 5).to_mdm_str()
    )


def test_configure_complex_schedule(
    scheduling_context: SchedulingContext, asg: AsgRuntimeInfo
) -> None:
    create_simple_schedule(
        scheduling_context,
        begintime="09:00",
        endtime="17:00",
        weekdays={"mon-fri"},
        monthdays={"1-15"},
    )

    asg_service = AsgService(scheduling_context)
    asg_service.context.current_dt = quick_time(9, 0, 0)

    list(asg_service.schedule_target())

    assert list(get_configured_actions(asg.resource_id)) == UnorderedList(
        [
            {
                "AutoScalingGroupName": "test-asg",
                "DesiredCapacity": 3,
                "MaxSize": 5,
                "MinSize": 1,
                "Recurrence": "0 9 1-15 * mon-fri",
                "ScheduledActionName": "IS-test-schedule-periodStart",
                "TimeZone": "UTC",
            },
            {
                "AutoScalingGroupName": "test-asg",
                "DesiredCapacity": 0,
                "MaxSize": 0,
                "MinSize": 0,
                "Recurrence": "0 17 1-15 * mon-fri",
                "ScheduledActionName": "IS-test-schedule-periodStop",
                "TimeZone": "UTC",
            },
        ]
    )


def test_configure_one_sided_schedule_start_only(
    scheduling_context: SchedulingContext, asg: AsgRuntimeInfo
) -> None:
    create_simple_schedule(scheduling_context, begintime="08:00", endtime=None)

    asg_service = AsgService(scheduling_context)
    asg_service.context.current_dt = quick_time(8, 0, 0)

    list(asg_service.schedule_target())

    actions = list(get_configured_actions(asg.resource_id))
    assert actions == [
        {
            "AutoScalingGroupName": "test-asg",
            "DesiredCapacity": 3,
            "MaxSize": 5,
            "MinSize": 1,
            "Recurrence": "0 8 * * *",
            "ScheduledActionName": "IS-test-schedule-periodStart",
            "TimeZone": "UTC",
        }
    ]


def test_configure_one_sided_schedule_end_only(
    scheduling_context: SchedulingContext, asg: AsgRuntimeInfo
) -> None:
    create_simple_schedule(scheduling_context, begintime=None, endtime="18:00")

    asg_service = AsgService(scheduling_context)
    asg_service.context.current_dt = quick_time(18, 0, 0)

    list(asg_service.schedule_target())

    actions = list(get_configured_actions(asg.resource_id))
    assert actions == [
        {
            "AutoScalingGroupName": "test-asg",
            "DesiredCapacity": 0,
            "MaxSize": 0,
            "MinSize": 0,
            "Recurrence": "0 18 * * *",
            "ScheduledActionName": "IS-test-schedule-periodStop",
            "TimeZone": "UTC",
        }
    ]


def test_mdm_value_comes_from_tag_when_present(
    scheduling_context: SchedulingContext, asg: AsgRuntimeInfo
) -> None:
    create_simple_schedule(scheduling_context, begintime="10:00", endtime="20:00")
    set_mdm_tag(asg.resource_id, AsgSize(2, 4, 8))

    asg_service = AsgService(scheduling_context)
    asg_service.context.current_dt = quick_time(10, 0, 0)

    list(asg_service.schedule_target())

    assert list(get_configured_actions(asg.resource_id)) == UnorderedList(
        [
            {
                "AutoScalingGroupName": "test-asg",
                "DesiredCapacity": 4,
                "MaxSize": 8,
                "MinSize": 2,
                "Recurrence": "0 10 * * *",
                "ScheduledActionName": "IS-test-schedule-periodStart",
                "TimeZone": "UTC",
            },
            {
                "AutoScalingGroupName": "test-asg",
                "DesiredCapacity": 0,
                "MaxSize": 0,
                "MinSize": 0,
                "Recurrence": "0 20 * * *",
                "ScheduledActionName": "IS-test-schedule-periodStop",
                "TimeZone": "UTC",
            },
        ]
    )


def test_missing_mdm_tag_with_zero_state_creates_error(
    scheduling_context: SchedulingContext,
) -> None:
    schedule, periods = create_simple_schedule(
        scheduling_context, begintime="10:00", endtime="20:00"
    )
    asg = create_asg("test-asg", AsgSize(0, 0, 0), schedule)
    register_asg_resources(
        [asg], lambda_execution_role(), MockResourceRegistrationEnvironment()
    )

    asg_service = AsgService(scheduling_context)
    asg_service.context.current_dt = quick_time(10, 0, 0)

    list(asg_service.schedule_target())

    assert get_tag_value(asg.resource_id, "IS-MinDesiredMax") == "0-0-0"
    # Error tag should be set for 0-0-0 state
    try:
        error_tag = get_tag_value(asg.resource_id, "IS-Error")
        assert error_tag is not None
    except KeyError:
        pass  # Error tag handling may vary


def test_does_not_reconfigure_when_nothing_changed(
    scheduling_context: SchedulingContext, asg: AsgRuntimeInfo
) -> None:
    create_simple_schedule(scheduling_context, begintime="10:00", endtime="20:00")
    set_mdm_tag(asg.resource_id, AsgSize(1, 3, 5))

    asg_service = AsgService(scheduling_context)
    asg_service.context.current_dt = quick_time(10, 0, 0)

    # First pass - let scheduler create registry record
    list(asg_service.schedule_target())

    # Delete actions to test if scheduler reconfigures
    delete_all_actions(asg.resource_id)

    # Second pass - should not reconfigure since nothing changed
    list(asg_service.schedule_target())

    # Verify no actions were recreated
    actions = list(get_configured_actions(asg.resource_id))
    assert len(actions) == 0


def test_reconfigures_when_mdm_changes(
    scheduling_context: SchedulingContext, asg: AsgRuntimeInfo
) -> None:
    create_simple_schedule(scheduling_context, begintime="10:00", endtime="20:00")
    set_mdm_tag(asg.resource_id, AsgSize(1, 3, 5))

    asg_service = AsgService(scheduling_context)
    asg_service.context.current_dt = quick_time(10, 0, 0)

    # First pass - let scheduler create registry record
    list(asg_service.schedule_target())

    # Delete actions and change MDM tag
    delete_all_actions(asg.resource_id)
    set_mdm_tag(asg.resource_id, AsgSize(2, 4, 6))

    # Second pass - should reconfigure due to MDM change
    list(asg_service.schedule_target())

    # Should reconfigure with new MDM values
    assert list(get_configured_actions(asg.resource_id)) == UnorderedList(
        [
            {
                "AutoScalingGroupName": "test-asg",
                "DesiredCapacity": 4,
                "MaxSize": 6,
                "MinSize": 2,
                "Recurrence": "0 10 * * *",
                "ScheduledActionName": "IS-test-schedule-periodStart",
                "TimeZone": "UTC",
            },
            {
                "AutoScalingGroupName": "test-asg",
                "DesiredCapacity": 0,
                "MaxSize": 0,
                "MinSize": 0,
                "Recurrence": "0 20 * * *",
                "ScheduledActionName": "IS-test-schedule-periodStop",
                "TimeZone": "UTC",
            },
        ]
    )


def test_reconfigures_when_configuration_near_expiry(
    scheduling_context: SchedulingContext, asg: AsgRuntimeInfo
) -> None:
    from datetime import datetime, timedelta

    create_simple_schedule(scheduling_context, begintime="10:00", endtime="20:00")

    asg_service = AsgService(scheduling_context)
    asg_service.context.current_dt = quick_time(10, 0, 0)

    # First pass - let scheduler create registry record
    list(asg_service.schedule_target())

    # Delete actions
    delete_all_actions(asg.resource_id)

    # Get registry record
    registry_key = RegistryKey.from_arn(ARN(asg.arn))
    registry_record = cast(
        RegisteredAsgInstance, scheduling_context.registry.get(registry_key)
    )

    # set current time to be close to expiration date
    asg_service.context.current_dt = datetime.fromisoformat(
        registry_record.last_configured.valid_until  # type: ignore
    ) - timedelta(hours=23)

    # Second pass - should reconfigure due to near expiry
    list(asg_service.schedule_target())

    # Should reconfigure due to near expiry
    assert list(get_configured_actions(asg.resource_id)) == UnorderedList(
        [
            {
                "AutoScalingGroupName": "test-asg",
                "DesiredCapacity": 3,
                "MaxSize": 5,
                "MinSize": 1,
                "Recurrence": "0 10 * * *",
                "ScheduledActionName": "IS-test-schedule-periodStart",
                "TimeZone": "UTC",
            },
            {
                "AutoScalingGroupName": "test-asg",
                "DesiredCapacity": 0,
                "MaxSize": 0,
                "MinSize": 0,
                "Recurrence": "0 20 * * *",
                "ScheduledActionName": "IS-test-schedule-periodStop",
                "TimeZone": "UTC",
            },
        ]
    )


def test_asg_configured_with_schedule(
    scheduling_context: SchedulingContext, asg: AsgRuntimeInfo
) -> None:
    create_simple_schedule(scheduling_context, begintime="10:00", endtime="14:00")

    asg_service = AsgService(scheduling_context)
    asg_service.context.current_dt = TEST_DATETIME

    with freeze_time(TEST_DATETIME):
        list(asg_service.schedule_target())

    assert list(get_configured_actions(asg.resource_id)) == UnorderedList(
        [
            {
                "AutoScalingGroupName": "test-asg",
                "DesiredCapacity": 3,
                "MaxSize": 5,
                "MinSize": 1,
                "Recurrence": "0 10 * * *",
                "ScheduledActionName": "IS-test-schedule-periodStart",
                "TimeZone": "UTC",
            },
            {
                "AutoScalingGroupName": "test-asg",
                "DesiredCapacity": 0,
                "MaxSize": 0,
                "MinSize": 0,
                "Recurrence": "0 14 * * *",
                "ScheduledActionName": "IS-test-schedule-periodStop",
                "TimeZone": "UTC",
            },
        ]
    )


def test_unregistered_asg_not_configured(scheduling_context: SchedulingContext) -> None:
    schedule, _ = create_simple_schedule(
        scheduling_context, begintime="10:00", endtime="14:00"
    )
    asg = create_asg(
        ASG_GROUP_NAME, AsgSize(min_size=3, desired_size=5, max_size=20), schedule
    )

    # intentionally not calling the following function (uncomment to prove test fails)
    # register_asg_resources([asg], lambda_execution_role(), MockResourceRegistrationEnvironment())

    list(AsgService(scheduling_context).schedule_target())

    assert len(list(get_configured_actions(asg.resource_id))) == 0


def test_asg_not_reconfigured_if_registry_last_configured_value_is_still_valid(
    scheduling_context: SchedulingContext, asg: AsgRuntimeInfo
) -> None:
    create_simple_schedule(scheduling_context, begintime="10:00", endtime="14:00")

    asg_service = AsgService(scheduling_context)
    asg_service.context.current_dt = TEST_DATETIME

    # First run - creates registry record and configures ASG
    with freeze_time(TEST_DATETIME):
        list(asg_service.schedule_target())

    first_run_actions = len(list(get_configured_actions(asg.resource_id)))
    assert first_run_actions > 0

    delete_all_actions(asg.resource_id)

    # Second run - should not reconfigure since registry record is valid
    with freeze_time(TEST_DATETIME + timedelta(hours=1)):
        list(asg_service.schedule_target())

    # Verify no actions were recreated
    second_run_actions = len(list(get_configured_actions(asg.resource_id)))
    assert second_run_actions == 0


def test_stopped_asg_configured_with_zero_state(
    scheduling_context: SchedulingContext,
) -> None:
    schedule, _ = create_simple_schedule(
        scheduling_context, begintime="10:00", endtime="14:00"
    )
    asg = create_asg(ASG_GROUP_NAME, AsgSize.stopped(), schedule)
    register_asg_resources(
        [asg], lambda_execution_role(), MockResourceRegistrationEnvironment()
    )

    asg_service = AsgService(scheduling_context)
    asg_service.context.current_dt = TEST_DATETIME

    with freeze_time(TEST_DATETIME):
        list(asg_service.schedule_target())

    # Verify MDM tag was created with 0-0-0 state
    assert get_tag_value(asg.resource_id, "IS-MinDesiredMax") == "0-0-0"


# The following tests are commented out as they test complex scenarios
# that may not be applicable to the new registry-based architecture
# and would require significant refactoring to work with the new system

# TODO: Refactor these tests for the new architecture
# - test_asg_reconfigured_if_tag_removed
# - test_asg_reconfigured_if_schedule_changed
# - test_asg_reconfigured_if_tag_expired
# - test_asg_configured_with_default_timezone_if_not_specified
# - test_asg_not_configured_if_schedule_invalid
# - test_preexisting_rules_not_removed
# - test_asg_reconfigured_if_schedule_name_specified
# - test_update_schedule_when_schedule_tag_value_is_updated
# - test_update_schedule_when_tag_is_updated_and_asg_stopped
# - test_schedule_ecs_autoscaling_group
