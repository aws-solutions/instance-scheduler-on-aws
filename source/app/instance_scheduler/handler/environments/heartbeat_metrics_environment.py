# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from dataclasses import dataclass
from os import environ
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from instance_scheduler.util.app_env_utils import AppEnvError, env_to_bool


@dataclass(frozen=True)
class HeartbeatMetricsEnvironment:
    config_table_name: str
    registry_table: str
    default_timezone: ZoneInfo
    enable_rds_snapshots: bool
    scheduler_frequency_minutes: int
    enable_aws_organizations: bool
    enable_ec2_ssm_maintenance_windows: bool
    ops_dashboard_enabled: bool

    @staticmethod
    def from_env() -> "HeartbeatMetricsEnvironment":
        try:
            return HeartbeatMetricsEnvironment(
                config_table_name=environ["CONFIG_TABLE"],
                registry_table=environ["REGISTRY_TABLE"],
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
            )
        except ZoneInfoNotFoundError as err:
            raise AppEnvError(f"Invalid timezone: {err.args[0]}") from err
        except KeyError as err:
            raise AppEnvError(
                f"Missing required application environment variable: {err.args[0]}"
            ) from err
