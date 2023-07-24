# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from dataclasses import replace
from os import environ
from typing import Optional
from unittest.mock import patch
from zoneinfo import ZoneInfo

from pytest import fixture, raises

import instance_scheduler.util.app_env
from instance_scheduler.util.app_env import (
    AppEnv,
    AppEnvError,
    _to_bool,
    _to_list,
    get_app_env,
)


@fixture(autouse=True)
def reset_cached_env() -> None:
    instance_scheduler.util.app_env._app_env = None


def test_to_bool() -> None:
    assert _to_bool("True")
    assert _to_bool("true")
    assert _to_bool("true ")
    assert _to_bool("Yes")
    assert _to_bool("yes")
    assert _to_bool(" yes")

    assert not _to_bool("")
    assert not _to_bool("False")
    assert not _to_bool("false")
    assert not _to_bool("\tfalse\r\n")
    assert not _to_bool("No")
    assert not _to_bool("no")
    assert not _to_bool("\tno")
    assert not _to_bool("Anything else")


def test_to_list() -> None:
    assert _to_list("") == []

    assert _to_list("a") == ["a"]
    assert _to_list("a,b,c") == ["a", "b", "c"]

    assert _to_list("foo,,bar") == ["foo", "bar"]
    assert _to_list("foo, bar, ") == ["foo", "bar"]
    assert _to_list("  ,   foo  , bar, ") == ["foo", "bar"]


def example_app_env() -> AppEnv:
    return AppEnv(
        scheduler_frequency_minutes=5,
        log_group="my-log-group",
        topic_arn="arn:aws:sns:us-east-1:123456789012:my-topic-arn",
        stack_name="my-stack-name",
        send_anonymous_metrics=False,
        solution_id="my-solution-id",
        solution_version="my-solution-version",
        enable_debug_logging=True,
        user_agent_extra="my-user-agent-extra",
        anonymous_metrics_url="my-metrics-url",
        stack_id="my-stack-id",
        uuid_key="my-uuid-key",
        start_ec2_batch_size=1,
        schedule_tag_key="my-schedule-tag-key",
        default_timezone=ZoneInfo("Asia/Tokyo"),
        enable_cloudwatch_metrics=True,
        enable_ec2_service=False,
        enable_rds_service=True,
        enable_rds_clusters=False,
        enable_rds_snapshots=True,
        schedule_regions=["us-east-1", "us-west-2"],
        app_namespace="my-app-namespace",
        scheduler_role_name="my-scheduler-role-name",
        enable_schedule_hub_account=False,
        enable_ec2_ssm_maintenance_windows=True,
        start_tags=["my-first-start-tag", "my-second-start-tag"],
        stop_tags=["my-stop-tag"],
        enable_aws_organizations=False,
        maintenance_window_table_name="my-maintenance-window-table",
        config_table_name="my-config-table-name",
        state_table_name="my-state-table-name",
    )


def env_from_app_env(app_env: AppEnv) -> dict[str, str]:
    return {
        "SCHEDULER_FREQUENCY": str(app_env.scheduler_frequency_minutes),
        "LOG_GROUP": app_env.log_group,
        "ISSUES_TOPIC_ARN": app_env.topic_arn,
        "STACK_NAME": app_env.stack_name,
        "SEND_METRICS": str(app_env.send_anonymous_metrics),
        "SOLUTION_ID": app_env.solution_id,
        "SOLUTION_VERSION": app_env.solution_version,
        "TRACE": str(app_env.enable_debug_logging),
        "USER_AGENT_EXTRA": app_env.user_agent_extra,
        "METRICS_URL": app_env.anonymous_metrics_url,
        "STACK_ID": app_env.stack_id,
        "UUID_KEY": app_env.uuid_key,
        "START_EC2_BATCH_SIZE": str(app_env.start_ec2_batch_size),
        "SCHEDULE_TAG_KEY": app_env.schedule_tag_key,
        "DEFAULT_TIMEZONE": str(app_env.default_timezone),
        "ENABLE_CLOUDWATCH_METRICS": str(app_env.enable_cloudwatch_metrics),
        "ENABLE_EC2_SERVICE": str(app_env.enable_ec2_service),
        "ENABLE_RDS_SERVICE": str(app_env.enable_rds_service),
        "ENABLE_RDS_CLUSTERS": str(app_env.enable_rds_clusters),
        "ENABLE_RDS_SNAPSHOTS": str(app_env.enable_rds_snapshots),
        "SCHEDULE_REGIONS": ", ".join(app_env.schedule_regions),
        "APP_NAMESPACE": app_env.app_namespace,
        "SCHEDULER_ROLE_NAME": app_env.scheduler_role_name,
        "ENABLE_SCHEDULE_HUB_ACCOUNT": str(app_env.enable_schedule_hub_account),
        "ENABLE_EC2_SSM_MAINTENANCE_WINDOWS": str(
            app_env.enable_ec2_ssm_maintenance_windows
        ),
        "START_TAGS": ", ".join(app_env.start_tags),
        "STOP_TAGS": ", ".join(app_env.stop_tags),
        "ENABLE_AWS_ORGANIZATIONS": str(app_env.enable_aws_organizations),
        "MAINTENANCE_WINDOW_TABLE": app_env.maintenance_window_table_name,
        "CONFIG_TABLE": app_env.config_table_name,
        "STATE_TABLE": app_env.state_table_name,
    }


def test_get_app_env() -> None:
    expected_env = example_app_env()

    app_env: Optional[AppEnv] = None
    with patch.dict(environ, env_from_app_env(expected_env), clear=True):
        app_env = get_app_env()
        assert get_app_env() is app_env

    assert app_env == expected_env


def test_missing_key() -> None:
    expected_env = example_app_env()
    my_env = env_from_app_env(expected_env)

    missing_key = "SCHEDULER_FREQUENCY"
    del my_env[missing_key]

    with patch.dict(environ, my_env, clear=True), raises(AppEnvError) as err:
        get_app_env()

    assert (
        str(err.value)
        == f"Missing required application environment variable: {missing_key}"
    )


def test_invalid_timezone() -> None:
    expected_env = example_app_env()
    my_env = env_from_app_env(expected_env)

    invalid_timezone = "something_invalid"
    my_env["DEFAULT_TIMEZONE"] = invalid_timezone

    with patch.dict(environ, my_env, clear=True), raises(AppEnvError) as err:
        get_app_env()

    assert (
        str(err.value)
        == f"Invalid timezone: No time zone found with key {invalid_timezone}"
    )


def test_scheduled_services() -> None:
    app_env = example_app_env()

    app_env_ec2_enabled = replace(
        app_env, enable_ec2_service=True, enable_rds_service=False
    )
    assert set(app_env_ec2_enabled.scheduled_services()) == {"ec2"}

    app_env_rds_enabled = replace(
        app_env, enable_ec2_service=False, enable_rds_service=True
    )
    assert set(app_env_rds_enabled.scheduled_services()) == {"rds"}

    app_env_both_enabled = replace(
        app_env, enable_ec2_service=True, enable_rds_service=True
    )
    assert set(app_env_both_enabled.scheduled_services()) == {"ec2", "rds"}
