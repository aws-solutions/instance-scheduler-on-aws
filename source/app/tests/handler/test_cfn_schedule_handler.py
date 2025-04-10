# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from datetime import time
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

from instance_scheduler.configuration.instance_schedule import InstanceSchedule
from instance_scheduler.configuration.running_period import RunningPeriod
from instance_scheduler.configuration.running_period_dict_element import (
    RunningPeriodDictElement,
)
from instance_scheduler.cron.cron_recurrence_expression import CronRecurrenceExpression
from instance_scheduler.cron.parser import (
    parse_monthdays_expr,
    parse_months_expr,
    parse_weekdays_expr,
)
from instance_scheduler.handler.cfn_schedule import (
    CfnScheduleHandler,
    CfnSchedulePeriodProperties,
    CfnScheduleResourceProperties,
)
from instance_scheduler.model.store.period_definition_store import PeriodDefinitionStore
from instance_scheduler.model.store.schedule_definition_store import (
    ScheduleDefinitionStore,
)
from instance_scheduler.util.custom_resource import CustomResourceRequest
from tests.context import MockLambdaContext
from tests.test_utils.any_nonempty_string import AnyNonEmptyString
from tests.test_utils.mock_main_lambda_env import MockMainLambdaEnv
from tests.test_utils.testsuite_env import TestSuiteEnv
from tests.test_utils.unordered_list import UnorderedList

stack_arn = "arn:aws:cloudformation:us-west-2:123456789012:stack/teststack/51af3dc0-da77-11e4-872e-1234567db123"


def new_create_request(
    resource_properties: CfnScheduleResourceProperties,
) -> CustomResourceRequest[CfnScheduleResourceProperties]:
    return {
        "RequestType": "Create",
        "ServiceToken": "LambdaARN",
        "ResponseURL": "url",
        "StackId": stack_arn,
        "RequestId": "requestId",
        "ResourceType": "Custom::ServiceInstanceSchedule",
        "LogicalResourceId": "CFNLogicalID",
        "PhysicalResourceId": "PhysicalID",
        "ResourceProperties": resource_properties,
        "OldResourceProperties": {},
    }


def new_update_request(
    new_resource_properties: CfnScheduleResourceProperties,
    old_resource_properties: CfnScheduleResourceProperties,
) -> CustomResourceRequest[CfnScheduleResourceProperties]:
    return {
        "RequestType": "Update",
        "ServiceToken": "LambdaARN",
        "ResponseURL": "url",
        "StackId": stack_arn,
        "RequestId": "requestId",
        "ResourceType": "Custom::ServiceInstanceSchedule",
        "LogicalResourceId": "CFNLogicalID",
        "PhysicalResourceId": "PhysicalID",
        "ResourceProperties": new_resource_properties,
        "OldResourceProperties": old_resource_properties,
    }


@patch.object(CfnScheduleHandler, "_send_response")
def test_minimalist_cfn_schedule_creation(
    mocked_cfn_callback: MagicMock,
    schedule_store: ScheduleDefinitionStore,
    period_store: PeriodDefinitionStore,
    test_suite_env: TestSuiteEnv,
) -> None:
    event = new_create_request(
        {
            "NoStackPrefix": "True",
            "ServiceToken": "serviceTokenARN",
            "Periods": [{"EndTime": "16:59"}],
        }
    )
    handler = CfnScheduleHandler(event, MockLambdaContext(), MockMainLambdaEnv())
    handler.handle_request()

    expected_schedule = InstanceSchedule(
        name="CFNLogicalID",
        configured_in_stack=stack_arn,
        timezone=test_suite_env.default_timezone,
        stop_new_instances=True,
        periods=[
            RunningPeriodDictElement(
                period=RunningPeriod(name=AnyNonEmptyString(), endtime=time(16, 59, 0))
            )
        ],
    )

    response = mocked_cfn_callback.call_args.args[0]
    assert response["Status"] == "SUCCESS", response["Reason"]
    # todo: appears to return timeout even for exceptions within code? (6/30/23)
    #            -- action: improve error reporting
    schedules = schedule_store.find_all()
    assert len(schedules) == 1
    assert "CFNLogicalID" in schedules
    saved_schedule = schedules["CFNLogicalID"].to_instance_schedule(period_store)
    assert saved_schedule == expected_schedule


@patch.object(CfnScheduleHandler, "_send_response")
def test_cfn_schedule_with_legacy_maint_win_str_type(
    mocked_cfn_callback: MagicMock,
    schedule_store: ScheduleDefinitionStore,
    period_store: PeriodDefinitionStore,
    test_suite_env: TestSuiteEnv,
) -> None:
    event = new_create_request(
        {
            "NoStackPrefix": "True",
            "ServiceToken": "serviceTokenARN",
            "Periods": [{"EndTime": "16:59"}],
            "SsmMaintenanceWindow": "my_window_name",  # backwards compatibility for str type
        }
    )
    handler = CfnScheduleHandler(event, MockLambdaContext(), MockMainLambdaEnv())
    handler.handle_request()

    expected_schedule = InstanceSchedule(
        name="CFNLogicalID",
        configured_in_stack=stack_arn,
        timezone=test_suite_env.default_timezone,
        ssm_maintenance_window=["my_window_name"],
        periods=[
            RunningPeriodDictElement(
                period=RunningPeriod(name=AnyNonEmptyString(), endtime=time(16, 59, 0))
            )
        ],
    )

    response = mocked_cfn_callback.call_args.args[0]
    assert response["Status"] == "SUCCESS", response["Reason"]
    schedules = schedule_store.find_all()
    assert len(schedules) == 1
    assert "CFNLogicalID" in schedules
    saved_schedule = schedules["CFNLogicalID"].to_instance_schedule(period_store)
    assert saved_schedule == expected_schedule


@patch.object(CfnScheduleHandler, "_send_response")
def test_cfn_schedule_with_all_parameters(
    mocked_cfn_callback: MagicMock,
    schedule_store: ScheduleDefinitionStore,
    period_store: PeriodDefinitionStore,
) -> None:
    event = new_create_request(
        {
            "ServiceToken": "ServiceTokenARN",
            "NoStackPrefix": "True",
            "Name": "schedule_name",
            "Description": "template with all values",
            "Timezone": "America/New_York",
            "Enforced": "True",
            "Hibernate": "True",
            "RetainRunning": "True",
            "StopNewInstances": "True",
            "UseMaintenanceWindow": "True",
            "SsmMaintenanceWindow": ["my_window_name"],
            "OverrideStatus": "running",
            "Periods": [
                {
                    "Description": "run from 9-5 on the first 3 days of March",
                    "BeginTime": "9:00",
                    "EndTime": "17:00",
                    "InstanceType": "t2.micro",
                    "MonthDays": "1-3",
                    "Months": "3",
                },
                {
                    "Description": "run from 2pm-5pm on the weekends",
                    "BeginTime": "14:00",
                    "EndTime": "17:00",
                    "InstanceType": "t2.micro",
                    "WeekDays": "Sat-Sun",
                },
            ],
            # deprecated fields that shouldn't cause the template to error
            "Metrics": "True",  # type: ignore[typeddict-unknown-key]
        }
    )

    expected_schedule = InstanceSchedule(
        name="schedule_name",
        description="template with all values",
        timezone=ZoneInfo("America/New_York"),
        configured_in_stack=stack_arn,
        enforced=True,
        hibernate=True,
        retain_running=True,
        stop_new_instances=True,
        ssm_maintenance_window=["my_window_name"],
        override_status="running",
        periods=UnorderedList(
            [
                RunningPeriodDictElement(
                    period=RunningPeriod(
                        name=AnyNonEmptyString(),
                        begintime=time(9, 0, 0),
                        endtime=time(17, 0, 0),
                        cron_recurrence=CronRecurrenceExpression(
                            monthdays=parse_monthdays_expr({"1-3"}),
                            months=parse_months_expr({"3"}),
                        ),
                    ),
                    instancetype="t2.micro",
                ),
                RunningPeriodDictElement(
                    period=RunningPeriod(
                        name=AnyNonEmptyString(),
                        begintime=time(14, 0, 0),
                        endtime=time(17, 0, 0),
                        cron_recurrence=CronRecurrenceExpression(
                            weekdays=parse_weekdays_expr({"sat-sun"}),
                        ),
                    ),
                    instancetype="t2.micro",
                ),
            ]
        ),
    )

    handler = CfnScheduleHandler(event, MockLambdaContext(), MockMainLambdaEnv())
    handler.handle_request()
    response = mocked_cfn_callback.call_args.args[0]
    assert response["Status"] == "SUCCESS", response["Reason"]
    schedules = schedule_store.find_all()
    assert len(schedules) == 1
    assert "schedule_name" in schedules
    saved_schedule = schedules["schedule_name"].to_instance_schedule(period_store)
    assert saved_schedule == expected_schedule

    # expect that all periods are also tagged with configured_in_stack parameter:
    for period in period_store.find_all().values():
        assert period.configured_in_stack == stack_arn


@patch.object(CfnScheduleHandler, "_send_response")
def test_cfn_schedule_fail_when_invalid_schedule_property_provided(
    mocked_cfn_callback: MagicMock,
    schedule_store: ScheduleDefinitionStore,
    period_store: PeriodDefinitionStore,
) -> None:
    event = new_create_request(
        {
            "ServiceToken": "serviceTokenARN",
            "NoStackPrefix": "True",
            "Timezone": "UTC",
            "Invalid": "Invalid parameter",  # Should fail as it is not a supported property
        }  # type: ignore[typeddict-unknown-key]
    )
    handler = CfnScheduleHandler(event, MockLambdaContext(), MockMainLambdaEnv())
    handler.handle_request()

    error_message = f"Unknown schedule property Invalid, valid properties are {CfnScheduleResourceProperties.__annotations__.keys()}"
    response = mocked_cfn_callback.call_args.args[0]
    assert response["Status"] == "FAILED"
    assert response["Reason"] == error_message

    schedules = schedule_store.find_all()
    periods = period_store.find_all()
    assert len(schedules) == 0
    assert len(periods) == 0


@patch.object(CfnScheduleHandler, "_send_response")
def test_cfn_schedule_fail_when_schedule_property_case_not_match(
    mocked_cfn_callback: MagicMock,
    schedule_store: ScheduleDefinitionStore,
    period_store: PeriodDefinitionStore,
) -> None:
    event = new_create_request(
        {
            "ServiceToken": "serviceTokenARN",
            "NoStackPrefix": "True",
            "TimeZone": "UTC",  # Should fail as `Timezone` is the expected property
            "Periods": [{"BeginTime": "00:00"}],
        }  # type: ignore[typeddict-unknown-key]
    )
    handler = CfnScheduleHandler(event, MockLambdaContext(), MockMainLambdaEnv())
    handler.handle_request()

    error_message = f"Unknown schedule property TimeZone, valid properties are {CfnScheduleResourceProperties.__annotations__.keys()}"
    response = mocked_cfn_callback.call_args.args[0]
    assert response["Status"] == "FAILED"
    assert response["Reason"] == error_message

    schedules = schedule_store.find_all()
    periods = period_store.find_all()
    assert len(schedules) == 0
    assert len(periods) == 0


@patch.object(CfnScheduleHandler, "_send_response")
def test_cfn_schedule_fail_when_schedule_period_empty(
    mocked_cfn_callback: MagicMock,
    schedule_store: ScheduleDefinitionStore,
    period_store: PeriodDefinitionStore,
) -> None:
    event = new_create_request(
        {
            "ServiceToken": "serviceTokenARN",
            "NoStackPrefix": "True",
            "Timezone": "UTC",
            "Periods": [],  # Should fail as it is empty
        },
    )
    handler = CfnScheduleHandler(event, MockLambdaContext(), MockMainLambdaEnv())
    handler.handle_request()

    logical_id = event["LogicalResourceId"]
    error_message = f"Error parsing schedule {logical_id}: At least one period must be specified for a schedule"
    response = mocked_cfn_callback.call_args.args[0]
    assert response["Status"] == "FAILED"
    assert response["Reason"] == error_message

    schedules = schedule_store.find_all()
    periods = period_store.find_all()
    assert len(schedules) == 0
    assert len(periods) == 0


@patch.object(CfnScheduleHandler, "_send_response")
def test_cfn_schedule_fail_when_invalid_schedule_period_provided(
    mocked_cfn_callback: MagicMock,
    schedule_store: ScheduleDefinitionStore,
    period_store: PeriodDefinitionStore,
) -> None:
    event = new_create_request(
        {
            "ServiceToken": "serviceTokenARN",
            "NoStackPrefix": "True",
            "Timezone": "UTC",
            "Periods": [
                {
                    "BeginTime": "00:00",
                    "EndTime": "01:00",
                    "Invalid": "Invalid parameter",  # Should fail as it is not a supported property
                }  # type: ignore[typeddict-unknown-key]
            ],
        },
    )
    handler = CfnScheduleHandler(event, MockLambdaContext(), MockMainLambdaEnv())
    handler.handle_request()

    error_message = f"Unknown period property Invalid, valid properties are {CfnSchedulePeriodProperties.__annotations__.keys()}"
    response = mocked_cfn_callback.call_args.args[0]
    assert response["Status"] == "FAILED"
    assert response["Reason"] == error_message

    schedules = schedule_store.find_all()
    periods = period_store.find_all()
    assert len(schedules) == 0
    assert len(periods) == 0


@patch.object(CfnScheduleHandler, "_send_response")
def test_cfn_schedule_fail_when_schedule_period_property_case_not_match(
    mocked_cfn_callback: MagicMock,
    schedule_store: ScheduleDefinitionStore,
    period_store: PeriodDefinitionStore,
) -> None:
    event = new_create_request(
        {
            "ServiceToken": "serviceTokenARN",
            "NoStackPrefix": "True",
            "Timezone": "UTC",
            "Periods": [
                {
                    "Endtime": "01:00",  # Should fail as `EndTime` is the expected property
                }  # type: ignore[typeddict-unknown-key]
            ],
        },
    )
    handler = CfnScheduleHandler(event, MockLambdaContext(), MockMainLambdaEnv())
    handler.handle_request()

    error_message = f"Unknown period property Endtime, valid properties are {CfnSchedulePeriodProperties.__annotations__.keys()}"
    response = mocked_cfn_callback.call_args.args[0]
    assert response["Status"] == "FAILED"
    assert response["Reason"] == error_message

    schedules = schedule_store.find_all()
    periods = period_store.find_all()
    assert len(schedules) == 0
    assert len(periods) == 0


@patch.object(CfnScheduleHandler, "_send_response")
def test_update_from_deprecated_schedule_format_to_valid_schedule_format_succeeds(
    mocked_cfn_callback: MagicMock,
    schedule_store: ScheduleDefinitionStore,
    period_store: PeriodDefinitionStore,
) -> None:
    """
    when updating from and older version of the solution to a newer version, it's possible
    that a schedule template which was previously valid for the old version is not valid on the new version
    due to deprecated/updated properties. These properties should fail when creating a new schedule (as tested above)
    but during an update we need to ensure that we can update the now invalid schedule to a new, valid format
    (this was a bug in 3.0.0-3.0.1)
    """

    invalid_schedule_req: CfnScheduleResourceProperties = {
        "NoStackPrefix": "True",
        "ServiceToken": "serviceTokenARN",
        "Periods": [{"EndTime": "16:59"}],
        "Metrics": "True",  # type: ignore[typeddict-unknown-key]
    }

    valid_schedule_req: CfnScheduleResourceProperties = {
        "NoStackPrefix": "True",
        "ServiceToken": "serviceTokenARN",
        "Periods": [{"EndTime": "16:59"}],
    }

    update_request = new_update_request(
        new_resource_properties=valid_schedule_req,
        old_resource_properties=invalid_schedule_req,
    )
    handler = CfnScheduleHandler(
        update_request, MockLambdaContext(), MockMainLambdaEnv()
    )
    handler.handle_request()
    response = mocked_cfn_callback.call_args.args[0]
    assert response["Status"] == "SUCCESS", response["Reason"]
