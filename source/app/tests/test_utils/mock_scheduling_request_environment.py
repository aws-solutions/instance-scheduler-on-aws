# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from contextlib import contextmanager
from dataclasses import dataclass
from os import environ
from typing import Iterator, Optional
from unittest.mock import patch
from zoneinfo import ZoneInfo

from instance_scheduler.handler.environments.scheduling_request_environment import (
    SchedulingRequestEnvironment,
)


@dataclass(frozen=True)
class MockSchedulingRequestEnvironment(SchedulingRequestEnvironment):
    user_agent_extra: str = "my-user-agent-extra"
    config_table_name: str = "my-config-table-name"
    maintenance_window_table_name: str = "my-maintenance-window-table"
    scheduler_role_name: str = "my-scheduler-role-name"
    default_timezone: ZoneInfo = ZoneInfo("Asia/Tokyo")
    schedule_tag_key: str = "Schedule"
    scheduler_frequency_minutes: int = 5
    enable_ec2_ssm_maintenance_windows: bool = False
    enable_rds_service: bool = True
    enable_rds_clusters: bool = True
    enable_docdb_service: bool = True
    enable_neptune_service: bool = True
    enable_rds_snapshots: bool = True
    enable_ops_monitoring: bool = True
    hub_stack_name: str = "my-hub-stack-name"
    scheduling_interval_minutes: int = 5
    config_table: str = "my-config-table-name"
    registry_table: str = "my-registry-table-name"
    ice_retry_queue_url: Optional[str] = (
        "https://sqs.us-east-1.amazonaws.com/123456789012/test-queue"
    )
    asg_scheduled_rule_prefix: str = "IS-"
    asg_metadata_tag_key: str = "scheduled"
    local_event_bus_name: str = "local-events"
    global_event_bus_name: str = "global-events"

    @contextmanager
    def patch_env(self, clear: bool = True) -> Iterator[None]:
        env_vars = {
            "USER_AGENT_EXTRA": self.user_agent_extra,
            "CONFIG_TABLE": self.config_table_name,
            "MAINT_WINDOW_TABLE": self.maintenance_window_table_name,
            "SCHEDULER_ROLE_NAME": self.scheduler_role_name,
            "DEFAULT_TIMEZONE": str(self.default_timezone),
            "SCHEDULE_TAG_KEY": self.schedule_tag_key,
            "ENABLE_EC2_SSM_MAINTENANCE_WINDOWS": str(
                self.enable_ec2_ssm_maintenance_windows
            ).lower(),
            "ENABLE_RDS_SERVICE": str(self.enable_rds_service).lower(),
            "ENABLE_RDS_CLUSTERS": str(self.enable_rds_clusters).lower(),
            "ENABLE_NEPTUNE_SERVICE": str(self.enable_neptune_service).lower(),
            "ENABLE_DOCDB_SERVICE": str(self.enable_docdb_service).lower(),
            "ENABLE_RDS_SNAPSHOTS": str(self.enable_rds_snapshots).lower(),
            "SCHEDULING_INTERVAL_MINUTES": str(self.scheduler_frequency_minutes),
            "ENABLE_OPS_MONITORING": str(self.enable_ops_monitoring).lower(),
            "HUB_STACK_NAME": self.hub_stack_name,
            "REGISTRY_TABLE": self.registry_table,
            "ICE_RETRY_SQS_URL": self.ice_retry_queue_url,
            "ASG_SCHEDULED_RULES_PREFIX": self.asg_scheduled_rule_prefix,
            "ASG_METADATA_TAG_KEY": self.asg_metadata_tag_key,
            "LOCAL_EVENT_BUS_NAME": self.local_event_bus_name,
            "GLOBAL_EVENT_BUS_NAME": self.global_event_bus_name,
        }
        with patch.dict(environ, {**environ, **env_vars}, clear=clear):
            yield
