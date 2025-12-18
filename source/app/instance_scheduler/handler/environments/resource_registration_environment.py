# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from dataclasses import dataclass
from os import environ

from instance_scheduler.configuration.scheduling_context import SchedulingEnvironment
from instance_scheduler.util.app_env_utils import AppEnvError


@dataclass(frozen=True)
class ResourceRegistrationEnvironment(SchedulingEnvironment):
    user_agent_extra: str
    config_table: str
    registry_table: str
    scheduler_role_name: str
    schedule_tag_key: str
    hub_stack_name: str
    scheduling_interval_minutes: int
    asg_scheduled_rule_prefix: str
    asg_metadata_tag_key: str
    local_event_bus_name: str
    global_event_bus_name: str

    @staticmethod
    def from_env() -> "ResourceRegistrationEnvironment":
        try:
            return ResourceRegistrationEnvironment(
                user_agent_extra=environ["USER_AGENT_EXTRA"],
                registry_table=environ["REGISTRY_TABLE"],
                config_table=environ["CONFIG_TABLE"],
                scheduler_role_name=environ["SCHEDULER_ROLE_NAME"],
                schedule_tag_key=environ["SCHEDULE_TAG_KEY"],
                hub_stack_name=environ["HUB_STACK_NAME"],
                scheduling_interval_minutes=int(environ["SCHEDULING_INTERVAL_MINUTES"]),
                asg_scheduled_rule_prefix=environ["ASG_SCHEDULED_RULES_PREFIX"],
                asg_metadata_tag_key=environ["ASG_METADATA_TAG_KEY"],
                local_event_bus_name=environ["LOCAL_EVENT_BUS_NAME"],
                global_event_bus_name=environ["GLOBAL_EVENT_BUS_NAME"],
            )
        except KeyError as err:
            raise AppEnvError(
                f"Missing required application environment variable: {err.args[0]}"
            ) from err
