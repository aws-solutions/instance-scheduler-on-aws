# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import os
from unittest.mock import patch
from instance_scheduler import configuration


def test_env_var_names():
    assert configuration.ENV_CONFIG == "CONFIG_TABLE"
    assert configuration.ENV_STATE == "STATE_TABLE"
    assert configuration.ENV_ACCOUNT == "ACCOUNT"
    assert configuration.ENV_STACK == "STACK_NAME"
    assert configuration.ENV_TAG_NAME == "TAG_NAME"
    assert configuration.ENV_SCHEDULE_FREQUENCY == "SCHEDULER_FREQUENCY"
    assert configuration.ENV_TRACE == "TRACE"
    assert (
        configuration.ENV_ENABLE_SSM_MAINTENANCE_WINDOWS
        == "ENABLE_SSM_MAINTENANCE_WINDOWS"
    )
    assert configuration.ENV_USER_AGENT == "USER_AGENT"
    assert configuration.ENV_SCHEDULER_RULE == "SCHEDULER_RULE"


def test_month_names():
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


def test_weekday_names():
    assert configuration.WEEKDAY_NAMES == [
        "mon",
        "tue",
        "wed",
        "thu",
        "fri",
        "sat",
        "sun",
    ]


def test_switch_values():
    assert configuration.SWITCH_VALUES == ["off", "on"]


def test_defaults():
    assert configuration.DEFAULT_TZ == "UTC"
    assert configuration.DEFAULT_TAGNAME == "Schedule"


def test_time_format_string():
    assert configuration.TIME_FORMAT_STRING == "%H:%M"


def test_attributes():
    assert configuration.TRACE == "trace"
    assert (
        configuration.ENABLE_SSM_MAINTENANCE_WINDOWS == "enable_SSM_maintenance_windows"
    )
    assert configuration.METRICS == "use_metrics"
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
    assert configuration.USE_MAINTENANCE_WINDOW == "use_maintenance_window"
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


def test_override_status():
    assert configuration.OVERRIDE_STATUS_STOPPED == "stopped"
    assert configuration.OVERRIDE_STATUS_RUNNING == "running"
    assert configuration.OVERRIDE_STATUS_VALUES == [
        configuration.OVERRIDE_STATUS_STOPPED,
        configuration.OVERRIDE_STATUS_RUNNING,
    ]


def test_instance_type_separator():
    assert configuration.INSTANCE_TYPE_SEP == "@"


def test_tag_values():
    assert configuration.TAG_VAL_SCHEDULER == "scheduler"
    assert configuration.TAG_VAL_MINUTE == "minute"
    assert configuration.TAG_VAL_HOUR == "hour"
    assert configuration.TAG_VAL_YEAR == "year"
    assert configuration.TAG_VAL_MONTH == "month"
    assert configuration.TAG_VAL_DAY == "day"
    assert configuration.TAG_VAL_TIMEZONE == "timezone"


def test_configuration_global():
    assert configuration.__configuration == None


@patch("instance_scheduler.configuration.SchedulerConfigBuilder")
@patch("instance_scheduler.configuration.ConfigDynamodbAdapter")
def test_get_scheduler_configuration(
    mock_config_dynamodb_adapter, mock_scheduler_config_builder
):
    my_configdata = "my config"
    mock_config_dynamodb_adapter.return_value.config = my_configdata
    expected_configuration = "expected configuration"
    mock_scheduler_config_builder.return_value.build.return_value = (
        expected_configuration
    )
    my_config_env = "my config env"

    with patch.dict(os.environ, {configuration.ENV_CONFIG: my_config_env}):
        result = configuration.get_scheduler_configuration(None)
        assert result == expected_configuration

    assert configuration.__configuration == expected_configuration
    mock_config_dynamodb_adapter.assert_called_once_with(my_config_env)
    mock_scheduler_config_builder.assert_called_once_with(logger=None)
    mock_scheduler_config_builder.return_value.build.assert_called_once_with(
        my_configdata
    )


def test_get_scheduler_configuration_already_set():
    my_configuration = "my configuration"
    configuration.__configuration = my_configuration
    assert configuration.get_scheduler_configuration(None) == my_configuration


def test_unload_scheduler_configuration():
    configuration.__configuration = {}
    configuration.unload_scheduler_configuration()
    assert configuration.__configuration == None
