# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from dataclasses import dataclass
from typing import Optional

from instance_scheduler.handler.environments.ice_retry_request_environment import (
    IceErrorRequestEnvironment,
)


@dataclass(frozen=True)
class MockIceRetryEnvironment(IceErrorRequestEnvironment):
    user_agent_extra: str = "test-agent"
    topic_arn: str = "arn:aws:sns:us-east-1:123456789012:test-topic"
    hub_stack_name: str = "test-stack"
    config_table_name: str = "test-config-table"
    scheduler_role_name: str = "test-scheduler-role"
    schedule_tag_key: str = "Schedule"
    scheduling_interval_minutes: int = 5
    enable_ec2_ssm_maintenance_windows: bool = False
    ice_retry_queue_url: Optional[str] = None
    config_table: str = "test-config-table"
    registry_table: str = "test-registry-table"
    maintenance_window_table_name: str = ""
    asg_scheduled_rule_prefix: str = "IS-"
    asg_metadata_tag_key: str = "scheduled"
    local_event_bus_name: str = "local-events"
    global_event_bus_name: str = "global-events"
