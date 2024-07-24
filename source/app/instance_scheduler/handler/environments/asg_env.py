# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from dataclasses import dataclass
from os import environ
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from instance_scheduler.util.app_env_utils import AppEnvError, env_to_bool


@dataclass(frozen=True)
class AsgEnv:
    user_agent_extra: str

    issues_topic_arn: str
    logger_raise_exceptions: bool

    config_table_name: str
    asg_scheduling_role_name: str
    default_timezone: ZoneInfo
    schedule_tag_key: str
    scheduled_tag_key: str
    rule_prefix: str

    @staticmethod
    def from_env() -> "AsgEnv":
        try:
            return AsgEnv(
                user_agent_extra=environ["USER_AGENT_EXTRA"],
                issues_topic_arn=environ["ISSUES_TOPIC_ARN"],
                logger_raise_exceptions=env_to_bool(
                    environ.get("LOGGER_RAISE_EXCEPTIONS", "False")
                ),
                config_table_name=environ["CONFIG_TABLE"],
                asg_scheduling_role_name=environ["ASG_SCHEDULING_ROLE_NAME"],
                default_timezone=ZoneInfo(environ["DEFAULT_TIMEZONE"]),
                schedule_tag_key=environ["SCHEDULE_TAG_KEY"],
                scheduled_tag_key=environ["SCHEDULED_TAG_KEY"],
                rule_prefix=environ["RULE_PREFIX"],
            )
        except ZoneInfoNotFoundError as err:
            raise AppEnvError(f"Invalid timezone: {err.args[0]}") from err
        except KeyError as err:
            raise AppEnvError(
                f"Missing required application environment variable: {err.args[0]}"
            ) from err
