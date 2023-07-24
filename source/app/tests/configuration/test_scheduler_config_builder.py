# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import datetime

from instance_scheduler.configuration.instance_schedule import Instance
from instance_scheduler.configuration.scheduler_config_builder import (
    SchedulerConfigBuilder,
)
from instance_scheduler.util.app_env import AppEnv
from tests.logger import MockLogger


def test_instance_schedule(app_env: AppEnv) -> None:
    logger = MockLogger()
    config_data = {
        "regions": {"us-east-1"},
        "scheduled_services": {"ec2"},
        "stopped_tags": "ScheduleMessage=Stopped on {year}/{month}/{day} at {hour}:{minute} {timezone}",
        "create_rds_snapshot": False,
        "default_timezone": "US/Eastern",
        "trace": True,
        "started_tags": "ScheduleMessage=Started on {year}/{month}/{day} at {hour}:{minute} {timezone}",
        "schedule_clusters": True,
        "name": "scheduler",
        "tagname": "Schedule",
        "type": "config",
        "periods": [
            {
                "months": {"jan/3"},
                "description": "Every first monday of each quarter",
                "weekdays": {"mon#1"},
                "name": "first-monday-in-quarter",
                "type": "period",
            },
            {
                "begintime": "09:00",
                "description": "Office hours",
                "endtime": "17:00",
                "weekdays": {"mon-fri"},
                "name": "office-hours",
                "type": "period",
            },
            {"endtime": "09:00", "name": "onlystop", "type": "period"},
            {"endtime": "13:00", "name": "onlystop1", "type": "period"},
            {
                "begintime": "09:00",
                "endtime": "10:00",
                "weekdays": {"mon-sun"},
                "name": "period1",
                "type": "period",
            },
            {
                "begintime": "17:00",
                "endtime": "18:00",
                "weekdays": {"mon#4"},
                "name": "period2",
                "type": "period",
            },
            {
                "begintime": "04:00",
                "endtime": "07:00",
                "weekdays": {"sat#4"},
                "name": "sat3",
                "type": "period",
            },
            {
                "begintime": "12:00",
                "endtime": "22:00",
                "weekdays": {"sat#4"},
                "name": "sat4",
                "type": "period",
            },
            {
                "begintime": "09:00",
                "endtime": "10:50",
                "weekdays": {"sun#4"},
                "name": "sun4",
                "type": "period",
            },
            {
                "begintime": "15:00",
                "endtime": "21:00",
                "weekdays": {"sun#4"},
                "name": "sun4-2",
                "type": "period",
            },
            {
                "begintime": "01:00",
                "weekdays": {"fri-sat"},
                "name": "test1",
                "type": "period",
            },
            {
                "begintime": "00:05",
                "endtime": "01:05",
                "weekdays": {"sat"},
                "name": "test12",
                "type": "period",
            },
            {
                "begintime": "09:00",
                "endtime": "12:00",
                "weekdays": {"mon-fri"},
                "name": "test2",
                "type": "period",
            },
            {
                "begintime": "11:00",
                "endtime": "13:00",
                "weekdays": {"mon-fro"},
                "name": "test3",
                "type": "period",
            },
            {
                "begintime": "11:00",
                "endtime": "15:00",
                "weekdays": {"mon-fri"},
                "name": "test4",
                "type": "period",
            },
            {
                "description": "Days in weekend",
                "weekdays": {"sat-sun"},
                "name": "weekends",
                "type": "period",
            },
            {
                "description": "Working days",
                "weekdays": {"mon-fri"},
                "name": "working-days",
                "type": "period",
            },
        ],
        "schedules": [
            {
                "timezone": "US/Eastern",
                "periods": {"period2", "period1"},
                "name": "describe1",
                "type": "schedule",
            },
            {
                "timezone": "US/Eastern",
                "periods": {"test4"},
                "name": "docDbSchedule",
                "type": "schedule",
            },
            {
                "periods": {"onlystop1", "onlystop"},
                "name": "onlystop",
                "type": "schedule",
            },
            {
                "description": "Retain running",
                "periods": {"office-hours"},
                "name": "running",
                "type": "schedule",
            },
            {
                "timezone": "US/Pacific",
                "description": "Office hours in Seattle (Pacific)",
                "periods": {"office-hours"},
                "name": "seattle-office-hours",
                "type": "schedule",
            },
            {"description": "Instances stopped", "name": "stopped", "type": "schedule"},
            {"periods": {"test3"}, "name": "test-error", "type": "schedule"},
            {
                "timezone": "US/Eastern",
                "periods": {"sat3", "sat4"},
                "name": "test-sat4",
                "type": "schedule",
            },
            {"periods": {"test12", "test1"}, "name": "test-ssm1", "type": "schedule"},
            {"periods": {"test1"}, "name": "test-ssm2", "type": "schedule"},
            {
                "description": "Testing config sun#4",
                "periods": {"sun4", "sun4-2"},
                "name": "test-sun4",
                "type": "schedule",
            },
            {"periods": {"test1"}, "name": "testMetrics", "type": "schedule"},
            {
                "timezone": "Europe/London",
                "description": "Office hours in UK",
                "periods": {"office-hours"},
                "name": "uk-office-hours",
                "type": "schedule",
            },
        ],
    }

    response = SchedulerConfigBuilder(logger=logger).build(config_data)

    schedule = response.get_schedule("running")
    assert schedule is not None

    instance = Instance(
        id="i-00bedf8a12df1dd6a",
        schedule_name="stopped",
        name="ISRelated",
        state=16,
        state_name="running",
        is_running=True,
        is_terminated=False,
        current_state="running",
        instancetype="t2.micro",
        tags={"Name": "ISRelated", "Schedule": "running"},
        account="111111111111",
        region="us-east-1",
        service="ec2",
        instance_str="EC2:i-00bedf8a12df1dd6a (ISRelated)",
        allow_resize=True,
        hibernate=False,
        maintenance_window=None,
    )

    current_test_execution_time = datetime.datetime.now(app_env.default_timezone)
    inst_state, _, valid_period = schedule.get_desired_state(
        instance, current_test_execution_time, logger=logger
    )

    # the configured period is a weekday mon-fri and time is between 9:00 AM and 5:00 PM.
    if current_test_execution_time.today().weekday() in [0, 1, 2, 3, 4]:
        if (
            current_test_execution_time.hour < 17
            and current_test_execution_time.hour > 9
        ):
            assert valid_period == "office-hours"
            assert inst_state == "running"
        else:
            assert valid_period is None
            assert inst_state == "stopped"
    else:
        assert valid_period is None
        assert inst_state == "stopped"
