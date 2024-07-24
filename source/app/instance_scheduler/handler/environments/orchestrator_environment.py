# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from dataclasses import dataclass
from os import environ
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from instance_scheduler.util.app_env_utils import AppEnvError, env_to_bool, env_to_list


@dataclass(frozen=True)
class OrchestratorEnvironment:
    # logging
    user_agent_extra: str
    log_group: str
    topic_arn: str
    enable_debug_logging: bool
    # references
    scheduling_request_handler_name: str
    config_table_name: str
    # scheduling
    enable_schedule_hub_account: bool
    enable_ec2_service: bool
    enable_rds_service: bool
    enable_rds_clusters: bool
    enable_neptune_service: bool
    enable_docdb_service: bool
    enable_asg_service: bool
    schedule_regions: list[str]

    # used for metrics only
    default_timezone: ZoneInfo
    enable_rds_snapshots: bool
    scheduler_frequency_minutes: int
    enable_aws_organizations: bool
    enable_ec2_ssm_maintenance_windows: bool
    ops_dashboard_enabled: bool
    start_tags: list[str]
    stop_tags: list[str]

    @staticmethod
    def from_env() -> "OrchestratorEnvironment":
        try:
            return OrchestratorEnvironment(
                user_agent_extra=environ["USER_AGENT_EXTRA"],
                log_group=environ["LOG_GROUP"],
                topic_arn=environ["ISSUES_TOPIC_ARN"],
                enable_debug_logging=env_to_bool(environ["ENABLE_DEBUG_LOGS"]),
                config_table_name=environ["CONFIG_TABLE"],
                scheduling_request_handler_name=environ[
                    "SCHEDULING_REQUEST_HANDLER_NAME"
                ],
                # scheduling
                enable_schedule_hub_account=env_to_bool(
                    environ["ENABLE_SCHEDULE_HUB_ACCOUNT"]
                ),
                enable_ec2_service=env_to_bool(environ["ENABLE_EC2_SERVICE"]),
                enable_rds_service=env_to_bool(environ["ENABLE_RDS_SERVICE"]),
                enable_rds_clusters=env_to_bool(environ["ENABLE_RDS_CLUSTERS"]),
                enable_neptune_service=env_to_bool(environ["ENABLE_NEPTUNE_SERVICE"]),
                enable_docdb_service=env_to_bool(environ["ENABLE_DOCDB_SERVICE"]),
                enable_asg_service=env_to_bool(environ["ENABLE_ASG_SERVICE"]),
                schedule_regions=env_to_list(environ["SCHEDULE_REGIONS"]),
                # metrics data
                default_timezone=ZoneInfo(environ["DEFAULT_TIMEZONE"]),
                enable_rds_snapshots=env_to_bool(environ["ENABLE_RDS_SNAPSHOTS"]),
                scheduler_frequency_minutes=int(environ["SCHEDULING_INTERVAL_MINUTES"]),
                enable_aws_organizations=env_to_bool(
                    environ["ENABLE_AWS_ORGANIZATIONS"]
                ),
                enable_ec2_ssm_maintenance_windows=env_to_bool(
                    environ["ENABLE_EC2_SSM_MAINTENANCE_WINDOWS"]
                ),
                ops_dashboard_enabled=env_to_bool(environ["OPS_DASHBOARD_ENABLED"]),
                start_tags=env_to_list(environ["START_TAGS"]),
                stop_tags=env_to_list(environ["STOP_TAGS"]),
            )
        except ZoneInfoNotFoundError as err:
            raise AppEnvError(f"Invalid timezone: {err.args[0]}") from err
        except KeyError as err:
            raise AppEnvError(
                f"Missing required application environment variable: {err.args[0]}"
            ) from err

    def scheduled_services(self) -> list[str]:
        result = []
        if self.enable_ec2_service:
            result.append("ec2")
        if (
            self.enable_rds_service
            or self.enable_rds_clusters
            or self.enable_neptune_service
            or self.enable_docdb_service
        ):
            result.append("rds")
        return result
