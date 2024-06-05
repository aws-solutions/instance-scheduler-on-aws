# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from dataclasses import dataclass, field
from zoneinfo import ZoneInfo

from instance_scheduler.handler.environments.orchestrator_environment import (
    OrchestratorEnvironment,
)


@dataclass(frozen=True)
class MockOrchestratorEnvironment(OrchestratorEnvironment):
    # logging
    user_agent_extra: str = "my-user-agent-extra"
    log_group: str = "my-log-group"
    topic_arn: str = "arn:aws:sns:us-east-1:123456789012:my-topic-arn"
    enable_debug_logging: bool = True
    # references
    scheduling_request_handler_name: str = "scheduling-request-handler-lambda"
    config_table_name: str = "my-config-table-name"
    # scheduling
    enable_schedule_hub_account: bool = False
    enable_ec2_service: bool = False
    enable_rds_service: bool = False
    enable_rds_clusters: bool = False
    enable_neptune_service: bool = False
    enable_docdb_service: bool = False
    enable_asg_service: bool = False
    schedule_regions: list[str] = field(default_factory=list)

    # used for metrics only
    default_timezone: ZoneInfo = ZoneInfo("Asia/Tokyo")
    enable_rds_snapshots: bool = True
    scheduler_frequency_minutes: int = 5
    enable_aws_organizations: bool = False
    enable_ec2_ssm_maintenance_windows: bool = False
    ops_dashboard_enabled: bool = True
    start_tags: list[str] = field(
        default_factory=lambda: ["my-first-start-tag", "my-second-start-tag"]
    )
    stop_tags: list[str] = field(default_factory=lambda: ["my-stop-tag"])
