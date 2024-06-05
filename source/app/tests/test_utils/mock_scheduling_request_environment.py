# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from dataclasses import dataclass, field
from zoneinfo import ZoneInfo

from instance_scheduler.handler.environments.scheduling_request_environment import (
    SchedulingRequestEnvironment,
)


@dataclass(frozen=True)
class MockSchedulingRequestEnvironment(SchedulingRequestEnvironment):
    user_agent_extra: str = "my-user-agent-extra"
    log_group: str = "my-log-group"
    topic_arn: str = "arn:aws:sns:us-east-1:123456789012:my-topic-arn"
    enable_debug_logging: bool = False
    stack_name: str = "my-stack-name"
    state_table_name: str = "my-state-table-name"
    config_table_name: str = "my-config-table-name"
    maintenance_window_table_name: str = "my-maintenance-window-table"
    scheduler_role_name: str = "my-scheduler-role-name"
    default_timezone: ZoneInfo = ZoneInfo("Asia/Tokyo")
    start_tags: list[str] = field(
        default_factory=lambda: ["my-first-start-tag", "my-second-start-tag"]
    )
    stop_tags: list[str] = field(default_factory=lambda: ["my-stop-tag"])
    schedule_tag_key: str = "Schedule"
    scheduler_frequency_minutes: int = 5
    enable_ec2_ssm_maintenance_windows: bool = False
    enable_rds_service: bool = True
    enable_rds_clusters: bool = True
    enable_docdb_service: bool = True
    enable_neptune_service: bool = True
    enable_rds_snapshots: bool = True
    enable_ops_monitoring: bool = True
