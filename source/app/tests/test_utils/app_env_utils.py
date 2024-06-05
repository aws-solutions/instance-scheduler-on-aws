# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import dataclasses
import os
from contextlib import contextmanager
from functools import wraps
from typing import Any, Callable, Iterator, TypeVar, cast
from unittest.mock import patch
from zoneinfo import ZoneInfo

import instance_scheduler.util.app_env
from instance_scheduler.util.app_env import AppEnv

FuncT = TypeVar("FuncT", bound=Callable[..., Any])


def with_mock_app_env(**overrides: Any) -> Callable[[FuncT], FuncT]:
    def decorator(func_to_decorate: FuncT) -> FuncT:
        @wraps(func_to_decorate)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            with mock_app_env(**overrides):
                func_to_decorate(*args, **kwargs)

        return cast(FuncT, wrapper)

    return decorator


@contextmanager
def mock_app_env(**overrides: Any) -> Iterator[AppEnv]:
    # clear cached env so that the new one is picked up
    old_env = instance_scheduler.util.app_env._app_env
    instance_scheduler.util.app_env._app_env = None
    app_env = dataclasses.replace(example_app_env(), **overrides)
    with patch.dict(os.environ, env_from_app_env(app_env)):
        yield app_env
    instance_scheduler.util.app_env._app_env = old_env


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
        schedule_tag_key="Schedule",
        default_timezone=ZoneInfo("Asia/Tokyo"),
        enable_ec2_service=True,
        enable_rds_service=True,
        enable_rds_clusters=False,
        enable_neptune_service=False,
        enable_docdb_service=False,
        enable_rds_snapshots=True,
        schedule_regions=["us-east-1", "us-west-2"],
        app_namespace="my-app-namespace",
        scheduler_role_name="my-scheduler-role-name",
        enable_schedule_hub_account=True,
        enable_ec2_ssm_maintenance_windows=False,
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
        "ENABLE_EC2_SERVICE": str(app_env.enable_ec2_service),
        "ENABLE_RDS_SERVICE": str(app_env.enable_rds_service),
        "ENABLE_RDS_CLUSTERS": str(app_env.enable_rds_clusters),
        "ENABLE_NEPTUNE_SERVICE": str(app_env.enable_neptune_service),
        "ENABLE_DOCDB_SERVICE": str(app_env.enable_docdb_service),
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
