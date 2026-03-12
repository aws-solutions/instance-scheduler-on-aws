# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from contextlib import contextmanager
from dataclasses import dataclass
from os import environ
from typing import Iterator
from unittest.mock import patch

from instance_scheduler.handler.spoke_registration import SpokeRegistrationEnvironment


@dataclass(frozen=True)
class MockSpokeRegistrationEnvironment(SpokeRegistrationEnvironment):
    user_agent_extra: str = "my-user-agent-extra"
    config_table: str = "my-config-table-name"
    registry_table: str = "my-registry-table-name"
    scheduler_role_name: str = "my-scheduler-role-name"
    schedule_tag_key: str = "Schedule"
    hub_stack_name: str = "my-hub-stack-name"
    scheduling_interval_minutes: int = 5
    asg_scheduled_rule_prefix: str = "my-asg-rule-prefix"
    asg_metadata_tag_key: str = "scheduled"
    local_event_bus_name: str = "local-events"
    global_event_bus_name: str = "global-events"
    ssm_param_path_name: str = "/IS/default/regions"
    ssm_param_update_role_name: str = "my-ssm-param-update-role-name"

    @contextmanager
    def patch_env(self, clear: bool = True) -> Iterator[None]:
        env_vars = {
            "USER_AGENT_EXTRA": self.user_agent_extra,
            "REGISTRY_TABLE": self.registry_table,
            "CONFIG_TABLE": self.config_table,
            "SCHEDULER_ROLE_NAME": self.scheduler_role_name,
            "SCHEDULE_TAG_KEY": self.schedule_tag_key,
            "HUB_STACK_NAME": self.hub_stack_name,
            "SCHEDULING_INTERVAL_MINUTES": str(self.scheduling_interval_minutes),
            "ASG_SCHEDULED_RULES_PREFIX": self.asg_scheduled_rule_prefix,
            "ASG_METADATA_TAG_KEY": self.asg_metadata_tag_key,
            "LOCAL_EVENT_BUS_NAME": self.local_event_bus_name,
            "GLOBAL_EVENT_BUS_NAME": self.global_event_bus_name,
            "SSM_PARAM_PATH_NAME": self.ssm_param_path_name,
            "SSM_PARAM_UPDATE_ROLE_NAME": self.ssm_param_update_role_name,
        }
        with patch.dict(environ, {**environ, **env_vars}, clear=clear):
            yield
