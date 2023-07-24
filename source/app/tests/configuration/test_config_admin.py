# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import json
from datetime import date, datetime

from pytest import raises

from instance_scheduler.configuration import config_admin
from instance_scheduler.configuration.config_admin import (
    ConfigAdmin,
    ConfigTableScheduleItem,
)
from instance_scheduler.util.app_env import AppEnv


def test_error_strings() -> None:
    assert config_admin.ERR_PERIOD_BEGIN_LATER_THAN_END == (
        "error: period begintime {} can not be later than endtime {}"
    )
    assert (
        config_admin.ERR_SCHEDULE_INVALID_OVERRIDE
        == "{} is not a valid value for {}, possible values are {}"
    )
    assert config_admin.ERR_SCHEDULE_OVERWRITE_OVERRIDE_EXCLUSIVE == (
        "{} option is mutually exclusive with {} option"
    )
    assert config_admin.ERR_CREATE_PERIOD_EXISTS == "error: period {} already exists"
    assert (
        config_admin.ERR_CREATE_SCHEDULE_EXISTS == "error: schedule {} already exists"
    )
    assert config_admin.ERR_DEL_PERIOD_IN_USE == (
        "error: period {} can not be deleted because it is still used in schedule(s) {}"
    )
    assert config_admin.ERR_PERIOD_NOT_FOUND == "not found: period {} does not exist"
    assert (
        config_admin.ERR_DEL_SCHEDULE_NAME_EMPTY
        == "error: schedule name parameter can not be empty"
    )
    assert (
        config_admin.ERR_SCHEDULE_NOT_FOUND == "not found: schedule {} does not exist"
    )
    assert (
        config_admin.ERR_EMPTY_PERIOD_NAME
        == "error: period name parameter can not be empty"
    )
    assert (
        config_admin.ERR_GET_SCHEDULE_NAME_EMPTY
        == "error: error schedule name parameter can not be empty"
    )
    assert config_admin.ERR_GET_USAGE_INVALID_END_DATE == (
        "error: invalid enddate {}, must be a valid date in format yyyymmdd {}"
    )
    assert config_admin.ERR_GET_USAGE_INVALID_START_DATE == (
        "error: invalid startdate {}, must be a valid date in format yyyymmdd {}"
    )
    assert config_admin.ERR_GET_USAGE_SCHEDULE_NAME_EMPTY == (
        "error: error schedule name parameter can not be empty"
    )
    assert config_admin.ERR_GET_USAGE_START_MUST_BE_LESS_OR_EQUAL_STOP == (
        "stop_date must be equal or later than start_date"
    )
    assert config_admin.ERR_NAME_PARAM_MISSING == "error: name parameter is missing"
    assert (
        config_admin.ERR_NO_PERIODS
        == "error: at least one period condition must be specified"
    )
    assert (
        config_admin.ERR_PERIOD_INVALID_MONTHDAYS
        == "error: {} is not a valid month days specification"
    )
    assert (
        config_admin.ERR_PERIOD_INVALID_MONTHS
        == "error: {} is not a valid months specification"
    )
    assert config_admin.ERR_PERIOD_INVALID_TIME == "error: {} {} is not a valid time"
    assert (
        config_admin.ERR_PERIOD_INVALID_WEEKDAYS
        == "error: {} is not a valid weekdays specification {}"
    )
    assert config_admin.ERR_PERIOD_UNKNOWN_PARAMETER == (
        "error: {} is not a valid parameter, valid parameters are {}"
    )
    assert (
        config_admin.ERR_SCHEDULE_INVALID_BOOLEAN
        == "error: {} for parameter {} is not a valid boolean value"
    )
    assert (
        config_admin.ERR_SCHEDULE_INVALID_TIMEZONE
        == "error: {} is not a valid time zone for parameter {}"
    )
    assert config_admin.ERR_SCHEDULE_NAME_MISSING == "error: name parameter is missing"
    assert (
        config_admin.ERR_SCHEDULE_NO_PERIOD
        == "error: at least one period must be specified for a schedule"
    )
    assert (
        config_admin.ERR_SCHEDULE_PERIOD_DOES_NOT_EXISTS
        == "error: not found: period {} does not exist"
    )
    assert config_admin.ERR_SCHEDULE_UNKNOWN_PARAMETER == (
        "error: {} is not a valid parameter, valid parameters are {}"
    )
    assert config_admin.ERR_UPDATE_INVALID_BOOL_PARAM == (
        "error: {} for parameter {} is not a valid boolean value"
    )
    assert (
        config_admin.ERR_UPDATE_INVALID_TZ_PARAMETER
        == "error: {} is not a valid time zone for parameter {}"
    )
    assert (
        config_admin.ERR_UPDATE_SCHEDULE_NAME_EMPTY
        == "error: schedule name parameter can not be empty"
    )
    assert (
        config_admin.ERR_UPDATE_TAGNAME_EMPTY
        == "error: tagname parameter must be specified"
    )
    assert (
        config_admin.ERR_UPDATE_UNKNOWN_PARAMETER
        == "error: {} is not a valid parameter"
    )
    assert config_admin.ERR_UPDATE_UNKNOWN_SERVICE == "{} is not a supported service"
    assert config_admin.ERR_STOP_MUST_BE_LATER_OR_EQUAL_TO_START == (
        "stop_date must be equal or later than start_date"
    )


def test_info_strings() -> None:
    assert config_admin.INF_ADD_ACCOUNT_EVENT_PERMISSION == (
        "Add permission for account {} to put events on message bus, sid is {}"
    )
    assert config_admin.INF_REMOVE_EVENT_PERMISSION == (
        "Remove permission for account {} to put events on event bus, sid = {}"
    )


def test_config_admin_type_attr() -> None:
    assert ConfigAdmin.TYPE_ATTR == "type"


def test_config_admin_time_regex() -> None:
    assert ConfigAdmin.TIME_REGEX == "^([0|1]?[0-9]|2[0-3]):[0-5][0-9]$"


def test_config_admin_supported_services() -> None:
    assert ConfigAdmin.SUPPORTED_SERVICES == ["ec2", "rds"]


def test_config_admin_table_name(app_env: AppEnv) -> None:
    assert ConfigAdmin(None, None).table_name == app_env.config_table_name


def test_custom_encoder_set() -> None:
    """Stringifies set as list"""
    assert json.dumps(set(), cls=ConfigAdmin.CustomEncoder) == "[]"

    items = [1, 2, 3]
    items_set = set(items)
    result = json.loads(json.dumps(items_set, cls=ConfigAdmin.CustomEncoder))
    assert isinstance(result, list)
    assert items_set == set(result)


def test_custom_encoder_datetime() -> None:
    """Stringifies datetimes in locale format without seconds"""
    dt_with_seconds = datetime(
        year=2023, month=5, day=11, hour=11, minute=41, second=20
    )
    dt_no_seconds = dt_with_seconds.replace(second=0)
    expected_str = f'"{dt_no_seconds.strftime("%x %X")}"'
    assert json.dumps(dt_with_seconds, cls=ConfigAdmin.CustomEncoder) == expected_str


def test_custom_encoder_invalid() -> None:
    """Errors on other types"""
    with raises(TypeError):
        json.dumps(date(year=2023, month=1, day=12), cls=ConfigAdmin.CustomEncoder)


def test_validate_schedule_no_periods() -> None:
    config = ConfigAdmin(None, None)

    with raises(ValueError) as err:
        config._validate_schedule(ConfigTableScheduleItem(name="my-schedule"))

    assert str(err.value) == config_admin.ERR_SCHEDULE_NO_PERIOD


def test_validate_schedule_override_no_periods() -> None:
    config = ConfigAdmin(None, None)
    schedule = ConfigTableScheduleItem(name="my-schedule", override_status="running")

    result = config._validate_schedule(schedule)

    schedule["type"] = "schedule"
    assert result == schedule
