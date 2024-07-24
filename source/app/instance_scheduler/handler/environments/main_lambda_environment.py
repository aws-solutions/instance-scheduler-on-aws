# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from dataclasses import dataclass
from os import environ

from instance_scheduler.util.app_env_utils import AppEnvError, env_to_bool


@dataclass(frozen=True)
class MainLambdaEnv:
    log_group: str
    topic_arn: str
    solution_version: str
    enable_debug_logging: bool
    user_agent_extra: str
    enable_aws_organizations: bool
    config_table_name: str

    @classmethod
    def from_env(cls) -> "MainLambdaEnv":
        try:
            return MainLambdaEnv(
                log_group=environ["LOG_GROUP"],
                topic_arn=environ["ISSUES_TOPIC_ARN"],
                solution_version=environ["SOLUTION_VERSION"],
                enable_debug_logging=env_to_bool(environ["TRACE"]),
                user_agent_extra=environ["USER_AGENT_EXTRA"],
                enable_aws_organizations=env_to_bool(
                    environ["ENABLE_AWS_ORGANIZATIONS"]
                ),
                config_table_name=environ["CONFIG_TABLE"],
            )
        except KeyError as err:
            raise AppEnvError(
                f"Missing required application environment variable: {err.args[0]}"
            ) from err
