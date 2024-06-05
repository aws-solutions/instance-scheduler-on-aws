# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from instance_scheduler import configuration


def test_month_names() -> None:
    assert configuration.MONTH_NAMES == [
        "jan",
        "feb",
        "mar",
        "apr",
        "may",
        "jun",
        "jul",
        "aug",
        "sep",
        "oct",
        "nov",
        "dec",
    ]


def test_weekday_names() -> None:
    assert configuration.WEEKDAY_NAMES == [
        "mon",
        "tue",
        "wed",
        "thu",
        "fri",
        "sat",
        "sun",
    ]


def test_switch_values() -> None:
    assert configuration.SWITCH_VALUES == ["off", "on"]


def test_defaults() -> None:
    assert configuration.DEFAULT_TZ == "UTC"
    assert configuration.DEFAULT_TAGNAME == "Schedule"


def test_time_format_string() -> None:
    assert configuration.TIME_FORMAT_STRING == "%H:%M"


def test_attributes() -> None:
    assert configuration.TRACE == "trace"
    assert (
        configuration.ENABLE_SSM_MAINTENANCE_WINDOWS == "enable_ssm_maintenance_windows"
    )
    assert configuration.REGIONS == "regions"
    assert configuration.BEGINTIME == "begintime"
    assert configuration.DESCRIPTION == "description"
    assert configuration.DEFAULT_TIMEZONE == "default_timezone"
    assert configuration.ENDTIME == "endtime"
    assert configuration.INSTANCE_TYPE == "instancetype"
    assert configuration.MONTHDAYS == "monthdays"
    assert configuration.MONTHS == "months"
    assert configuration.NAME == "name"
    assert configuration.OVERWRITE == "overwrite"
    assert configuration.OVERRIDE_STATUS == "override_status"
    assert configuration.PERIODS == "periods"
    assert configuration.PERIOD == "period"
    assert configuration.SCHEDULES == "schedules"
    assert configuration.SCHEDULED_SERVICES == "scheduled_services"
    assert configuration.SCHEDULE_CLUSTERS == "schedule_clusters"
    assert configuration.CREATE_RDS_SNAPSHOT == "create_rds_snapshot"
    assert configuration.STOP_NEW_INSTANCES == "stop_new_instances"
    assert configuration.SSM_MAINTENANCE_WINDOW == "ssm_maintenance_window"
    assert configuration.TIMEZONE == "timezone"
    assert configuration.TAGNAME == "tagname"
    assert configuration.WEEKDAYS == "weekdays"
    assert configuration.SCHEDULE_LAMBDA_ACCOUNT == "schedule_lambda_account"
    assert configuration.ENFORCED == "enforced"
    assert configuration.HIBERNATE == "hibernate"
    assert configuration.RETAINED_RUNNING == "retain_running"
    assert configuration.STARTED_TAGS == "started_tags"
    assert configuration.STOPPED_TAGS == "stopped_tags"
    assert configuration.SCHEDULE_CONFIG_STACK == "configured_in_stack"


def test_override_status() -> None:
    assert configuration.OVERRIDE_STATUS_STOPPED == "stopped"
    assert configuration.OVERRIDE_STATUS_RUNNING == "running"
    assert configuration.OVERRIDE_STATUS_VALUES == [
        configuration.OVERRIDE_STATUS_STOPPED,
        configuration.OVERRIDE_STATUS_RUNNING,
    ]


def test_instance_type_separator() -> None:
    assert configuration.INSTANCE_TYPE_SEP == "@"


def test_tag_values() -> None:
    assert configuration.TAG_VAL_SCHEDULER == "scheduler"
    assert configuration.TAG_VAL_MINUTE == "minute"
    assert configuration.TAG_VAL_HOUR == "hour"
    assert configuration.TAG_VAL_YEAR == "year"
    assert configuration.TAG_VAL_MONTH == "month"
    assert configuration.TAG_VAL_DAY == "day"
    assert configuration.TAG_VAL_TIMEZONE == "timezone"
