# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from contextlib import contextmanager
from dataclasses import dataclass
from os import environ
from typing import Iterator
from unittest.mock import patch
from zoneinfo import ZoneInfo

from instance_scheduler.handler.environments.heartbeat_metrics_environment import (
    HeartbeatMetricsEnvironment,
)


@dataclass(frozen=True)
class MockHeartbeatMetricsEnvironment(HeartbeatMetricsEnvironment):
    config_table_name: str = "my-config-table-name"
    registry_table: str = "my-registry-table-name"
    default_timezone: ZoneInfo = ZoneInfo("UTC")
    enable_rds_snapshots: bool = False
    scheduler_frequency_minutes: int = 5
    enable_aws_organizations: bool = False
    enable_ec2_ssm_maintenance_windows: bool = False
    ops_dashboard_enabled: bool = False

    @contextmanager
    def patch_env(self, clear: bool = True) -> Iterator[None]:
        env_vars = {
            "CONFIG_TABLE": self.config_table_name,
            "REGISTRY_TABLE": self.registry_table,
            "DEFAULT_TIMEZONE": str(self.default_timezone),
            "ENABLE_RDS_SNAPSHOTS": str(self.enable_rds_snapshots).lower(),
            "SCHEDULING_INTERVAL_MINUTES": str(self.scheduler_frequency_minutes),
            "ENABLE_AWS_ORGANIZATIONS": str(self.enable_aws_organizations).lower(),
            "ENABLE_EC2_SSM_MAINTENANCE_WINDOWS": str(
                self.enable_ec2_ssm_maintenance_windows
            ).lower(),
            "OPS_DASHBOARD_ENABLED": str(self.ops_dashboard_enabled).lower(),
        }
        with patch.dict(environ, {**environ, **env_vars}, clear=clear):
            yield
