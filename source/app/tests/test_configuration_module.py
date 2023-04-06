# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

from instance_scheduler.util.logger import Logger
import datetime
from instance_scheduler.configuration.scheduler_config_builder import SchedulerConfigBuilder

def test_scheduler_config_builder():
    LOG_STREAM = "{}-{:0>4d}{:0>2d}{:0>2d}"
    dt = datetime.datetime.utcnow()
    logstream = LOG_STREAM.format(
        "test_configuration_module", dt.year, dt.month, dt.day
    )
    logger = Logger(
        logstream=logstream,
        buffersize=30,
        context={},
        loggroup="test_configuration_module",
    )
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
            {
                "description": "monday start",
                "weekdays": {"mon"},
                "name": "monstart",
                "type": "period",
                "begintime": "09:00",
            },
            {
                "description": "run all day tuesday thursday",
                "weekdays": {"tue-thu"},
                "name": "tuethu",
                "type": "period",
                "begintime": "00:00",
                "endtime": "23:59",
            },
            {
                "description": "stop friday five pm",
                "weekdays": {"fri"},
                "name": "fridaystop",
                "type": "period",
                "begintime": "00:00",
                "endtime": "17:00",
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
                "timezone": "US/Pacific",
                "periods": {"monstart", "tuethu", "fridaystop"},
                "name": "monstartandfridayend",
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
                "timezone": "US/Eastern",
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
            {
                "timezone": "Asia/Macau",
                "periods": {"test12", "test1"},
                "name": "test-ssm1",
                "type": "schedule",
            },
            {"periods": {"test1"}, "name": "test-ssm2", "type": "schedule"},
            {
                "description": "Testing config sun#4",
                "periods": {"sun4", "sun4-2"},
                "name": "test-sun4",
                "type": "schedule",
            },
            {
                "timezone": "US/Eastern",
                "periods": {"test1"},
                "name": "testMetrics",
                "type": "schedule",
            },
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
    assert response.scheduled_services == {"ec2"}
    assert response.default_timezone == "US/Eastern"
    assert response.tag_name == "Schedule"
    assert response.create_rds_snapshot == False
    assert response.regions == {"us-east-1"}
    assert response.remote_account_ids == []

    for schedule_name in response.schedules:
        if schedule_name == "docDbSchedule":
            assert response.get_schedule(schedule_name).timezone == "US/Eastern"
            for period in response.get_schedule(schedule_name).periods:
                valid_current_datetime = datetime.datetime(
                    2021, 6, 18, 14, 5, 59, 342380
                )
                assert (
                    period.get("period").get_desired_state(
                        logger, valid_current_datetime
                    )
                    == "running"
                )

                invalid_datetime = datetime.datetime(2021, 6, 20, 17, 30, 59, 34258)
                assert (
                    period.get("period").get_desired_state(logger, invalid_datetime)
                    == "stopped"
                )

        if schedule_name == "monstartandfridayend":
            assert response.get_schedule(schedule_name).timezone == "US/Pacific"
            for period in response.get_schedule(schedule_name).periods:
                if period.get("period").name == "tuethu":
                    tuesday_nine_am = datetime.datetime(2021, 9, 14, 9, 0, 00, 0)
                    assert (
                        period.get("period").get_desired_state(logger, tuesday_nine_am)
                        == "running"
                    )
                if period.get("period").name == "fridaystop":
                    friday_five_fifteen_pm = datetime.datetime(
                        2021, 9, 17, 17, 15, 00, 0
                    )
                    assert (
                        period.get("period").get_desired_state(
                            logger, friday_five_fifteen_pm
                        )
                        == "stopped"
                    )
                    friday_four_fortyfive_pm = datetime.datetime(
                        2021, 9, 17, 16, 45, 00, 0
                    )
                    assert (
                        period.get("period").get_desired_state(
                            logger, friday_four_fortyfive_pm
                        )
                        == "running"
                    )
                    sat_four_fortyfive_pm = datetime.datetime(
                        2021, 9, 18, 16, 45, 00, 0
                    )
                    assert (
                        period.get("period").get_desired_state(
                            logger, sat_four_fortyfive_pm
                        )
                        == "stopped"
                    )
                    sunday_four_fortyfive_pm = datetime.datetime(
                        2021, 9, 19, 16, 45, 00, 0
                    )
                    assert (
                        period.get("period").get_desired_state(
                            logger, sunday_four_fortyfive_pm
                        )
                        == "stopped"
                    )
