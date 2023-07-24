# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

from instance_scheduler import configuration
from instance_scheduler.configuration.scheduler_config import GlobalConfig
from instance_scheduler.util.app_env import AppEnv

mock_config = GlobalConfig(
    scheduled_services=["ec2"],
    schedule_clusters=True,
    tag_name="tag",
    regions=["us-east-1"],
    default_timezone=ZoneInfo("UTC"),
    schedules={},
    trace=False,
    enable_ssm_maintenance_windows=True,
    use_metrics=True,
    remote_account_ids=["123456789012"],
    namespace="ns",
    aws_partition="aws",
    scheduler_role_name="rolename",
    organization_id="",
    schedule_lambda_account=False,
    create_rds_snapshot=True,
    started_tags="",
    stopped_tags="",
)


def test_env_var_names() -> None:
    assert configuration.ENV_STACK == "STACK_NAME"


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


def test_configuration_global() -> None:
    assert configuration.__configuration is None


@patch("instance_scheduler.configuration.SchedulerConfigBuilder")
@patch("instance_scheduler.configuration.ConfigDynamodbAdapter")
def test_get_scheduler_configuration(
    mock_config_dynamodb_adapter: MagicMock,
    mock_scheduler_config_builder: MagicMock,
    app_env: AppEnv,
) -> None:
    my_configdata = "my config"
    mock_config_dynamodb_adapter.return_value.config = my_configdata
    expected_configuration = mock_config
    mock_scheduler_config_builder.return_value.build.return_value = (
        expected_configuration
    )

    result = configuration.get_global_configuration(None)
    assert result == expected_configuration

    assert configuration.__configuration == expected_configuration
    mock_config_dynamodb_adapter.assert_called_once_with(app_env.config_table_name)
    mock_scheduler_config_builder.assert_called_once_with(logger=None)
    mock_scheduler_config_builder.return_value.build.assert_called_once_with(
        my_configdata
    )


def test_get_scheduler_configuration_already_set() -> None:
    configuration.__configuration = mock_config
    assert configuration.get_global_configuration(None) == mock_config


def test_unload_scheduler_configuration() -> None:
    configuration.__configuration = mock_config
    configuration.unload_global_configuration()
    assert configuration.__configuration is None
