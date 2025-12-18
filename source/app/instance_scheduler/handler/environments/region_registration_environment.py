# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from dataclasses import dataclass
from os import environ

from instance_scheduler.util.app_env_utils import AppEnvError


@dataclass
class RegionRegistrationEnvironment:
    user_agent_extra: str
    hub_account_id: str
    stack_id: str
    ssm_param_path: str
    hub_registration_function_arn: str
    hub_registration_role_name: str

    @staticmethod
    def from_env() -> "RegionRegistrationEnvironment":
        try:
            return RegionRegistrationEnvironment(
                user_agent_extra=environ["USER_AGENT_EXTRA"],
                hub_account_id=environ["HUB_ACCOUNT_ID"],
                stack_id=environ["STACK_ID"],
                ssm_param_path=environ["SSM_PARAM_PATH"],
                hub_registration_function_arn=environ["HUB_REGISTRATION_FUNCTION_ARN"],
                hub_registration_role_name=environ["HUB_REGISTRATION_ROLE_NAME"],
            )

        except KeyError as err:
            raise AppEnvError(
                f"Missing required application environment variable: {err.args[0]}"
            ) from err
