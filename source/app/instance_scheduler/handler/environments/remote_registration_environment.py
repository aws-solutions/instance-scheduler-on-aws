# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from dataclasses import dataclass
from os import environ

from instance_scheduler.util.app_env_utils import AppEnvError


@dataclass
class RemoteRegistrationEnvironment:
    user_agent_extra: str
    hub_registration_lambda_arn: str

    @staticmethod
    def from_env() -> "RemoteRegistrationEnvironment":
        try:
            return RemoteRegistrationEnvironment(
                user_agent_extra=environ["USER_AGENT_EXTRA"],
                hub_registration_lambda_arn=environ["HUB_REGISTRATION_LAMBDA_ARN"],
            )
        except KeyError as err:
            raise AppEnvError(
                f"Missing required application environment variable: {err.args[0]}"
            ) from err
