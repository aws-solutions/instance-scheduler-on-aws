# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from dataclasses import dataclass
from os import environ
from zoneinfo import ZoneInfoNotFoundError

from instance_scheduler.util.app_env_utils import AppEnvError


@dataclass(frozen=True)
class OrchestratorEnvironment:
    user_agent_extra: str
    scheduling_request_handler_name: str
    config_table_name: str
    registry_table: str

    @staticmethod
    def from_env() -> "OrchestratorEnvironment":
        try:
            return OrchestratorEnvironment(
                user_agent_extra=environ["USER_AGENT_EXTRA"],
                config_table_name=environ["CONFIG_TABLE"],
                registry_table=environ["REGISTRY_TABLE"],
                scheduling_request_handler_name=environ[
                    "SCHEDULING_REQUEST_HANDLER_NAME"
                ],
            )
        except ZoneInfoNotFoundError as err:
            raise AppEnvError(f"Invalid timezone: {err.args[0]}") from err
        except KeyError as err:
            raise AppEnvError(
                f"Missing required application environment variable: {err.args[0]}"
            ) from err
