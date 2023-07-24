# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from datetime import time
from unittest.mock import ANY, MagicMock, patch

from instance_scheduler.configuration import get_global_configuration
from instance_scheduler.configuration.instance_schedule import InstanceSchedule
from instance_scheduler.configuration.running_period import RunningPeriod
from instance_scheduler.configuration.running_period_dict_element import (
    RunningPeriodDictElement,
)
from instance_scheduler.handler.cfn_schedule import (
    CfnScheduleHandler,
    CfnScheduleResourceProperties,
)
from instance_scheduler.util.custom_resource import CustomResourceRequest
from tests.context import MockLambdaContext
from tests.logger import MockLogger
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
    }


@patch.object(CfnScheduleHandler, "_send_response")
def test_minimalist_cfn_schedule_creation(
    mocked_cfn_callback: MagicMock, config_table: None
) -> None:
    event = new_create_request(
        {
            "NoStackPrefix": "True",
            "ServiceToken": "serviceTokenARN",
            "Periods": [{"Description": "Stop at 5pm", "EndTime": "16:59"}],
        }
    )
    handler = CfnScheduleHandler(event, MockLambdaContext())
    handler.handle_request()

    expected_schedule = InstanceSchedule(
        name="CFNLogicalID",
        configured_in_stack=stack_arn,
        stop_new_instances=True,
        use_metrics=False,
        description="",
        periods=[
            RunningPeriodDictElement(
                period=RunningPeriod(name=ANY, endtime=time(16, 59, 0)),
                instancetype=None,
            )
        ],
    )

    assert handler.response["Status"] == "SUCCESS", handler.response[
        "Reason"
    ]  # todo: appears to return timeout even for exceptions within code? (6/30/23)
    #            -- action: improve error reporting
    global_config = get_global_configuration(MockLogger())
    assert len(global_config.schedules) == 1
    assert "CFNLogicalID" in global_config.schedules
    assert global_config.schedules["CFNLogicalID"] == expected_schedule


@patch.object(CfnScheduleHandler, "_send_response")
def test_cfn_schedule_with_all_parameters(
    mocked_cfn_callback: MagicMock, config_table: None
) -> None:
    # untested properties:
    # "Overwrite"
    # "OverrideStatus"
    # "Metrics"

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
            "SsmMaintenanceWindow": "my_window_name",
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
        }
    )

    expected_schedule = InstanceSchedule(
        name="schedule_name",
        description="template with all values",
        timezone="America/New_York",
        configured_in_stack=stack_arn,
        enforced=True,
        hibernate=True,
        retain_running=True,
        stop_new_instances=True,
        use_maintenance_window=True,
        ssm_maintenance_window="my_window_name",
        use_metrics=False,
        periods=UnorderedList(
            [
                RunningPeriodDictElement(
                    period=RunningPeriod(
                        name=ANY,
                        begintime=time(9, 0, 0),
                        endtime=time(17, 0, 0),
                        monthdays={1, 2, 3},
                        months={3},
                    ),
                    instancetype="t2.micro",
                ),
                RunningPeriodDictElement(
                    period=RunningPeriod(
                        name=ANY,
                        begintime=time(14, 0, 0),
                        endtime=time(17, 0, 0),
                        weekdays={5, 6},
                    ),
                    instancetype="t2.micro",
                ),
            ]
        ),
    )

    handler = CfnScheduleHandler(event, MockLambdaContext())
    handler.handle_request()

    assert handler.response["Status"] == "SUCCESS", handler.response["Reason"]
    global_config = get_global_configuration(MockLogger())
    assert len(global_config.schedules) == 1
    assert "schedule_name" in global_config.schedules
    saved_schedule = global_config.schedules["schedule_name"]
    assert saved_schedule == expected_schedule
