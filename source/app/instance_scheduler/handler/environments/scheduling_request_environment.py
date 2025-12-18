# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from dataclasses import dataclass
from os import environ
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from instance_scheduler.configuration.scheduling_context import SchedulingEnvironment
from instance_scheduler.util.app_env_utils import AppEnvError, env_to_bool


@dataclass(frozen=True)
class SchedulingRequestEnvironment(SchedulingEnvironment):
    user_agent_extra: str
    ice_retry_queue_url: Optional[str]
    hub_stack_name: str
    config_table_name: str
    maintenance_window_table_name: str
    scheduler_role_name: str

    config_table: str
    registry_table: str
    scheduling_interval_minutes: int
    asg_scheduled_rule_prefix: str
    asg_metadata_tag_key: str  # deprecated property, needed for migration purposes only
    local_event_bus_name: str
    global_event_bus_name: str

    default_timezone: ZoneInfo
    schedule_tag_key: str
    enable_ops_monitoring: bool

    # for ec2
    scheduler_frequency_minutes: int
    enable_ec2_ssm_maintenance_windows: bool

    # for rds
    enable_rds_snapshots: bool

    @staticmethod
    def from_env() -> "SchedulingRequestEnvironment":
        try:
            return SchedulingRequestEnvironment(
                user_agent_extra=environ["USER_AGENT_EXTRA"],
                config_table_name=environ["CONFIG_TABLE"],
                maintenance_window_table_name=environ["MAINT_WINDOW_TABLE"],
                scheduler_role_name=environ["SCHEDULER_ROLE_NAME"],
                default_timezone=ZoneInfo(environ["DEFAULT_TIMEZONE"]),
                schedule_tag_key=environ["SCHEDULE_TAG_KEY"],
                enable_ec2_ssm_maintenance_windows=env_to_bool(
                    environ["ENABLE_EC2_SSM_MAINTENANCE_WINDOWS"]
                ),
                enable_rds_snapshots=env_to_bool(environ["ENABLE_RDS_SNAPSHOTS"]),
                scheduler_frequency_minutes=int(environ["SCHEDULING_INTERVAL_MINUTES"]),
                local_event_bus_name=environ["LOCAL_EVENT_BUS_NAME"],
                global_event_bus_name=environ["GLOBAL_EVENT_BUS_NAME"],
                enable_ops_monitoring=env_to_bool(environ["ENABLE_OPS_MONITORING"]),
                hub_stack_name=environ["HUB_STACK_NAME"],
                scheduling_interval_minutes=int(environ["SCHEDULING_INTERVAL_MINUTES"]),
                config_table=environ["CONFIG_TABLE"],
                registry_table=environ["REGISTRY_TABLE"],
                ice_retry_queue_url=environ["ICE_RETRY_SQS_URL"],
                asg_scheduled_rule_prefix=environ["ASG_SCHEDULED_RULES_PREFIX"],
                asg_metadata_tag_key=environ["ASG_METADATA_TAG_KEY"],
            )
        except ZoneInfoNotFoundError as err:
            raise AppEnvError(f"Invalid timezone: {err.args[0]}") from err
        except KeyError as err:
            raise AppEnvError(
                f"Missing required application environment variable: {err.args[0]}"
            ) from err
