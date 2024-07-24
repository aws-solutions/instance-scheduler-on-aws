# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from dataclasses import dataclass
from os import environ
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from instance_scheduler.util.app_env_utils import AppEnvError, env_to_bool, env_to_list


@dataclass(frozen=True)
class SchedulingRequestEnvironment:
    user_agent_extra: str
    log_group: str
    topic_arn: str
    enable_debug_logging: bool
    stack_name: str
    state_table_name: str
    config_table_name: str
    maintenance_window_table_name: str
    scheduler_role_name: str

    default_timezone: ZoneInfo
    start_tags: list[str]
    stop_tags: list[str]
    schedule_tag_key: str
    enable_ops_monitoring: bool

    # for ec2
    scheduler_frequency_minutes: int
    enable_ec2_ssm_maintenance_windows: bool

    # for rds
    enable_rds_service: bool
    enable_rds_clusters: bool
    enable_docdb_service: bool
    enable_neptune_service: bool
    enable_rds_snapshots: bool

    @staticmethod
    def from_env() -> "SchedulingRequestEnvironment":
        try:
            return SchedulingRequestEnvironment(
                user_agent_extra=environ["USER_AGENT_EXTRA"],
                log_group=environ["LOG_GROUP"],
                topic_arn=environ["ISSUES_TOPIC_ARN"],
                enable_debug_logging=env_to_bool(environ["ENABLE_DEBUG_LOGS"]),
                stack_name=environ["STACK_NAME"],
                config_table_name=environ["CONFIG_TABLE"],
                state_table_name=environ["STATE_TABLE"],
                maintenance_window_table_name=environ["MAINT_WINDOW_TABLE"],
                scheduler_role_name=environ["SCHEDULER_ROLE_NAME"],
                default_timezone=ZoneInfo(environ["DEFAULT_TIMEZONE"]),
                start_tags=env_to_list(environ["START_TAGS"]),
                stop_tags=env_to_list(environ["STOP_TAGS"]),
                schedule_tag_key=environ["SCHEDULE_TAG_KEY"],
                enable_ec2_ssm_maintenance_windows=env_to_bool(
                    environ["ENABLE_EC2_SSM_MAINTENANCE_WINDOWS"]
                ),
                enable_rds_service=env_to_bool(environ["ENABLE_RDS_SERVICE"]),
                enable_rds_clusters=env_to_bool(environ["ENABLE_RDS_CLUSTERS"]),
                enable_neptune_service=env_to_bool(environ["ENABLE_NEPTUNE_SERVICE"]),
                enable_docdb_service=env_to_bool(environ["ENABLE_DOCDB_SERVICE"]),
                enable_rds_snapshots=env_to_bool(environ["ENABLE_RDS_SNAPSHOTS"]),
                scheduler_frequency_minutes=int(environ["SCHEDULING_INTERVAL_MINUTES"]),
                enable_ops_monitoring=env_to_bool(environ["ENABLE_OPS_MONITORING"]),
            )
        except ZoneInfoNotFoundError as err:
            raise AppEnvError(f"Invalid timezone: {err.args[0]}") from err
        except KeyError as err:
            raise AppEnvError(
                f"Missing required application environment variable: {err.args[0]}"
            ) from err
