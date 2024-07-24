# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from dataclasses import dataclass
from os import environ

from instance_scheduler.util.app_env_utils import AppEnvError, env_to_bool, env_to_list


@dataclass(frozen=True)
class AsgOrchEnv:
    user_agent_extra: str

    issues_topic_arn: str
    logger_raise_exceptions: bool

    config_table_name: str
    enable_schedule_hub_account: bool
    schedule_regions: list[str]
    asg_scheduler_name: str

    @staticmethod
    def from_env() -> "AsgOrchEnv":
        try:
            return AsgOrchEnv(
                user_agent_extra=environ["USER_AGENT_EXTRA"],
                issues_topic_arn=environ["ISSUES_TOPIC_ARN"],
                logger_raise_exceptions=env_to_bool(
                    environ.get("LOGGER_RAISE_EXCEPTIONS", "False")
                ),
                config_table_name=environ["CONFIG_TABLE"],
                enable_schedule_hub_account=env_to_bool(
                    environ["ENABLE_SCHEDULE_HUB_ACCOUNT"]
                ),
                schedule_regions=env_to_list(environ["SCHEDULE_REGIONS"]),
                asg_scheduler_name=environ["ASG_SCHEDULER_NAME"],
            )
        except KeyError as err:
            raise AppEnvError(
                f"Missing required application environment variable: {err.args[0]}"
            ) from err
