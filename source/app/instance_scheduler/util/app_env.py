# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from dataclasses import dataclass
from os import environ
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


@dataclass(frozen=True)
class AppEnv:
    scheduler_frequency_minutes: int
    log_group: str
    topic_arn: str
    stack_name: str
    send_anonymous_metrics: bool
    solution_id: str
    solution_version: str
    enable_debug_logging: bool
    user_agent_extra: str
    anonymous_metrics_url: str
    stack_id: str
    uuid_key: str
    start_ec2_batch_size: int
    schedule_tag_key: str
    default_timezone: ZoneInfo
    enable_cloudwatch_metrics: bool
    enable_ec2_service: bool
    enable_rds_service: bool
    enable_rds_clusters: bool
    enable_rds_snapshots: bool
    schedule_regions: list[str]
    app_namespace: str
    scheduler_role_name: str
    enable_schedule_hub_account: bool
    enable_ec2_ssm_maintenance_windows: bool
    start_tags: list[str]
    stop_tags: list[str]
    enable_aws_organizations: bool
    maintenance_window_table_name: str
    config_table_name: str
    state_table_name: str

    def scheduled_services(self) -> list[str]:
        result = []
        if self.enable_ec2_service:
            result.append("ec2")
        if self.enable_rds_service:
            result.append("rds")
        return result


# cache the application environment for warm starts
_app_env: Optional[AppEnv] = None


def get_app_env() -> AppEnv:
    """
    Retrieve the current application environment. This function should be called once
    per Lambda execution.

    Do not pass around the environment object. Do not retrieve the environment object
    whenever a environment setting is needed. Do not retrieve settings directly from the
    environment except where required for initialization order reasons.

    Most classes only need a small number of environment settings. The top-level Lambda
    handler should pass the needed values to the constructor for that class. This allows
    lower-level classes to remain testable with only the options they require rather
    than every option required by the entire system. It also prevents the environment
    class from becoming bloated with other runtime information.
    """
    global _app_env
    if not _app_env:
        _app_env = _from_environment()
    return _app_env


class AppEnvError(RuntimeError):
    pass


def _from_environment() -> AppEnv:
    try:
        return AppEnv(
            scheduler_frequency_minutes=int(environ["SCHEDULER_FREQUENCY"]),
            log_group=environ["LOG_GROUP"],
            topic_arn=environ["ISSUES_TOPIC_ARN"],
            stack_name=environ["STACK_NAME"],
            send_anonymous_metrics=_to_bool(environ["SEND_METRICS"]),
            solution_id=environ["SOLUTION_ID"],
            solution_version=environ["SOLUTION_VERSION"],
            enable_debug_logging=_to_bool(environ["TRACE"]),
            user_agent_extra=environ["USER_AGENT_EXTRA"],
            anonymous_metrics_url=environ["METRICS_URL"],
            stack_id=environ["STACK_ID"],
            uuid_key=environ["UUID_KEY"],
            start_ec2_batch_size=int(environ["START_EC2_BATCH_SIZE"]),
            schedule_tag_key=environ["SCHEDULE_TAG_KEY"],
            default_timezone=ZoneInfo(environ["DEFAULT_TIMEZONE"]),
            enable_cloudwatch_metrics=_to_bool(environ["ENABLE_CLOUDWATCH_METRICS"]),
            enable_ec2_service=_to_bool(environ["ENABLE_EC2_SERVICE"]),
            enable_rds_service=_to_bool(environ["ENABLE_RDS_SERVICE"]),
            enable_rds_clusters=_to_bool(environ["ENABLE_RDS_CLUSTERS"]),
            enable_rds_snapshots=_to_bool(environ["ENABLE_RDS_SNAPSHOTS"]),
            schedule_regions=_to_list(environ["SCHEDULE_REGIONS"]),
            app_namespace=environ["APP_NAMESPACE"],
            scheduler_role_name=environ["SCHEDULER_ROLE_NAME"],
            enable_schedule_hub_account=_to_bool(
                environ["ENABLE_SCHEDULE_HUB_ACCOUNT"]
            ),
            enable_ec2_ssm_maintenance_windows=_to_bool(
                environ["ENABLE_EC2_SSM_MAINTENANCE_WINDOWS"]
            ),
            start_tags=_to_list(environ["START_TAGS"]),
            stop_tags=_to_list(environ["STOP_TAGS"]),
            enable_aws_organizations=_to_bool(environ["ENABLE_AWS_ORGANIZATIONS"]),
            maintenance_window_table_name=environ["MAINTENANCE_WINDOW_TABLE"],
            config_table_name=environ["CONFIG_TABLE"],
            state_table_name=environ["STATE_TABLE"],
        )
    except ZoneInfoNotFoundError as err:
        raise AppEnvError(f"Invalid timezone: {err.args[0]}") from err
    except KeyError as err:
        raise AppEnvError(
            f"Missing required application environment variable: {err.args[0]}"
        ) from err


def _to_bool(value: str) -> bool:
    return value.strip().lower() in {"true", "yes"}


def _to_list(value: str) -> list[str]:
    items = []
    for item in value.split(","):
        stripped = item.strip()
        if stripped:
            items.append(stripped)
    return items
