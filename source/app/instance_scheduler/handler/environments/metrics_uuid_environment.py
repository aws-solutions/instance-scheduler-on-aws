# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from dataclasses import dataclass
from os import environ

from instance_scheduler.util.app_env_utils import AppEnvError


@dataclass
class MetricsUuidEnvironment:
    user_agent_extra: str
    stack_id: str
    uuid_key: str

    @staticmethod
    def from_env() -> "MetricsUuidEnvironment":
        try:
            return MetricsUuidEnvironment(
                user_agent_extra=environ["USER_AGENT_EXTRA"],
                stack_id=environ["STACK_ID"],
                uuid_key=environ["UUID_KEY"],
            )
        except KeyError as err:
            raise AppEnvError(
                f"Missing required application environment variable: {err.args[0]}"
            ) from err
