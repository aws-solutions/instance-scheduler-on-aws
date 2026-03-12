# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from contextlib import contextmanager
from dataclasses import dataclass
from os import environ
from typing import Iterator, Optional
from unittest.mock import patch

from instance_scheduler.handler.environments.resize_request_environment import (
    ResizeRequestEnvironment,
)
from tests.test_utils.mock_environs.mock_environment import MockEnvironment


@dataclass(frozen=True)
class MockResizeEnvironment(ResizeRequestEnvironment, MockEnvironment):
    user_agent_extra: str = "my-user-agent-extra"
    topic_arn: str = "arn:aws:sns:us-east-1:123456789012:test-topic"
    hub_stack_name: str = "my-hub-stack-name"
    config_table_name: str = "my-config-table-name"
    scheduler_role_name: str = "my-scheduler-role-name"
    schedule_tag_key: str = "Schedule"
    scheduling_interval_minutes: int = 5
    enable_ec2_ssm_maintenance_windows: bool = False
    resize_request_queue_url: Optional[str] = (
        "https://sqs.us-east-1.amazonaws.com/123456789012/test-queue"
    )
    config_table: str = "my-config-table-name"
    registry_table: str = "my-registry-table-name"
    maintenance_window_table_name: str = ""
    asg_scheduled_rule_prefix: str = "IS-"
    asg_metadata_tag_key: str = "scheduled"
    local_event_bus_name: str = "local-events"
    global_event_bus_name: str = "global-events"

    @contextmanager
    def patch_env(self, clear: bool = True) -> Iterator[None]:
        env_vars = {
            "USER_AGENT_EXTRA": self.user_agent_extra,
            "ISSUES_TOPIC_ARN": self.topic_arn,
            "STACK_NAME": self.hub_stack_name,
            "CONFIG_TABLE": self.config_table_name,
            "SCHEDULER_ROLE_NAME": self.scheduler_role_name,
            "SCHEDULE_TAG_KEY": self.schedule_tag_key,
            "SCHEDULING_INTERVAL_MINUTES": str(self.scheduling_interval_minutes),
            "REGISTRY_TABLE": self.registry_table,
            "ASG_SCHEDULED_RULES_PREFIX": self.asg_scheduled_rule_prefix,
            "ASG_METADATA_TAG_KEY": self.asg_metadata_tag_key,
            "LOCAL_EVENT_BUS_NAME": self.local_event_bus_name,
            "GLOBAL_EVENT_BUS_NAME": self.global_event_bus_name,
        }
        with patch.dict(environ, {**environ, **env_vars}, clear=clear):
            yield
