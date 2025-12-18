# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from dataclasses import dataclass
from os import environ
from typing import Optional

from instance_scheduler.configuration.scheduling_context import SchedulingEnvironment
from instance_scheduler.util.app_env_utils import AppEnvError


@dataclass(frozen=True)
class IceErrorRequestEnvironment(SchedulingEnvironment):
    user_agent_extra: str
    topic_arn: str
    hub_stack_name: str
    config_table_name: str
    scheduler_role_name: str
    schedule_tag_key: str
    scheduling_interval_minutes: int
    asg_scheduled_rule_prefix: str
    asg_metadata_tag_key: str
    enable_ec2_ssm_maintenance_windows: bool
    ice_retry_queue_url: Optional[str]
    local_event_bus_name: str
    global_event_bus_name: str

    config_table: str
    registry_table: str
    maintenance_window_table_name: str

    @staticmethod
    def from_env() -> "IceErrorRequestEnvironment":
        try:
            return IceErrorRequestEnvironment(
                user_agent_extra=environ["USER_AGENT_EXTRA"],
                topic_arn=environ["ISSUES_TOPIC_ARN"],
                config_table_name=environ["CONFIG_TABLE"],
                scheduler_role_name=environ["SCHEDULER_ROLE_NAME"],
                hub_stack_name=environ["STACK_NAME"],
                config_table=environ["CONFIG_TABLE"],
                registry_table=environ["REGISTRY_TABLE"],
                schedule_tag_key=environ["SCHEDULE_TAG_KEY"],
                scheduling_interval_minutes=int(environ["SCHEDULING_INTERVAL_MINUTES"]),
                enable_ec2_ssm_maintenance_windows=False,
                ice_retry_queue_url=None,
                maintenance_window_table_name="",
                asg_scheduled_rule_prefix=environ["ASG_SCHEDULED_RULES_PREFIX"],
                asg_metadata_tag_key=environ["ASG_METADATA_TAG_KEY"],
                local_event_bus_name=environ["LOCAL_EVENT_BUS_NAME"],
                global_event_bus_name=environ["GLOBAL_EVENT_BUS_NAME"],
            )
        except KeyError as err:
            raise AppEnvError(
                f"Missing required application environment variable: {err.args[0]}"
            ) from err
