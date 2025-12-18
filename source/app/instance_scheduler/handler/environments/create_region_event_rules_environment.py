# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from dataclasses import dataclass
from os import environ

from instance_scheduler.util.app_env_utils import AppEnvError


@dataclass(frozen=True)
class CreateRegionEventRulesEnvironment:
    tagging_event_rule_role_arn: str
    tagging_event_bus_arn: str
    tagging_event_rule_name_prefix: str
    user_agent_extra: str
    power_tools_service_name: str
    schedule_tag_key: str
    version: str
    regional_event_bus_name: str

    @classmethod
    def from_env(cls) -> "CreateRegionEventRulesEnvironment":
        try:
            return CreateRegionEventRulesEnvironment(
                tagging_event_rule_role_arn=environ["TAGGING_EVENT_RULE_ROLE_ARN"],
                tagging_event_bus_arn=environ["TAGGING_EVENT_BUS_ARN"],
                tagging_event_rule_name_prefix=environ["EVENT_RULE_PREFIX"],
                user_agent_extra=environ["USER_AGENT_EXTRA"],
                power_tools_service_name=environ["POWERTOOLS_SERVICE_NAME"],
                schedule_tag_key=environ["SCHEDULE_TAG_KEY"],
                version=environ["VERSION"],
                regional_event_bus_name=environ["REGIONAL_EVENT_BUS_NAME"],
            )
        except KeyError as err:
            raise AppEnvError(
                f"Missing required application environment variable: {err.args[0]}"
            ) from err
