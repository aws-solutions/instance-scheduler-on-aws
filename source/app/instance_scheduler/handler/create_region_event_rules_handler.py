# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import json
from enum import Enum
from typing import TYPE_CHECKING, Any, Final, List, Mapping, TypedDict

from aws_lambda_powertools import Logger
from botocore.exceptions import ClientError
from instance_scheduler.handler.environments.create_region_event_rules_environment import (
    CreateRegionEventRulesEnvironment,
)
from instance_scheduler.observability.powertools_logging import (
    powertools_logger,
    should_log_events,
)
from instance_scheduler.util.custom_resource import (
    CustomResource,
    CustomResourceResponse,
)
from instance_scheduler.util.session_manager import (
    lambda_execution_role,
)
from urllib3 import PoolManager

if TYPE_CHECKING:
    from aws_lambda_powertools.utilities.typing import LambdaContext
    from mypy_boto3_events import EventBridgeClient
else:
    LambdaContext = object
    EventBridgeClient = object

http = PoolManager()

logger: Final = powertools_logger()


class EventRuleSuffixes(Enum):
    RESOURCE_TAGGING_EVENT_RULE = "resource-tagging"
    ASG_TAGGING_EVENT_RULE = "asg-tagging"


@logger.inject_lambda_context(log_event=should_log_events(logger))
def lambda_handler(event: Mapping[str, Any], context: LambdaContext) -> None:
    try:
        env = CreateRegionEventRulesEnvironment.from_env()
        handler = CreateRegionEventRulesHandler(event, context, logger, env)
        handler.handle_request()
    except Exception as error:
        logger.error(
            f"Error occurred while running custom resource lambda with error {error}"
        )
        response_body = {
            "Status": "FAILED",
            "Reason": f"Custom resource failed with error: {error}",
            "PhysicalResourceId": event.get("LogicalResourceId"),
            "StackId": event.get("StackId"),
            "RequestId": event.get("RequestId"),
            "LogicalResourceId": event.get("LogicalResourceId"),
        }

        headers = {"Content-Type": "application/json"}
        http.request(
            "PUT",
            event.get("ResponseURL", ""),
            headers=headers,
            body=json.dumps(response_body),
        )


class CreateRegionEventRulesProperties(TypedDict):
    regions: List[str]


class CreateRegionEventRulesHandler(CustomResource[CreateRegionEventRulesProperties]):
    def __init__(
        self,
        event: Any,
        context: LambdaContext,
        logger: Logger,
        env: CreateRegionEventRulesEnvironment,
    ) -> None:
        super().__init__(event, context)
        self._logger: Final = logger
        self._env: Final = env

    def handle_request(self) -> None:
        """
        Handles the custom resource request to write scheduler global settings to config database
        :return:
        """
        CustomResource.handle_request(self)

    def _get_asg_rule_name(self) -> str:
        return f"{self._env.tagging_event_rule_name_prefix}-{EventRuleSuffixes.ASG_TAGGING_EVENT_RULE.value}"

    def _get_resource_rule_name(self) -> str:
        return f"{self._env.tagging_event_rule_name_prefix}-{EventRuleSuffixes.RESOURCE_TAGGING_EVENT_RULE.value}"

    def _create_regional_event_bus(self, events_client: EventBridgeClient) -> None:
        try:
            events_client.create_event_bus(Name=self._env.regional_event_bus_name)
        except ClientError as client_error:
            if (
                client_error.response["Error"]["Code"]
                == "ResourceAlreadyExistsException"
            ):
                return
            else:
                raise client_error

    def _delete_regional_event_bus(self, events_client: EventBridgeClient) -> None:
        try:
            events_client.delete_event_bus(Name=self._env.regional_event_bus_name)
        except ClientError as client_error:
            if client_error.response["Error"]["Code"] == "ResourceNotFoundException":
                return
            else:
                raise client_error

    def _create_event_rule(self, events_client: EventBridgeClient) -> bool:
        try:
            asg_tagging_event_pattern: Mapping[str, Any] = {
                "source": ["aws.autoscaling"],
                "detail-type": ["AWS API Call via CloudTrail"],
                "detail": {
                    "eventSource": ["autoscaling.amazonaws.com"],
                    "eventName": ["CreateOrUpdateTags", "DeleteTags"],
                    "requestParameters": {
                        "tags": {"key": [self._env.schedule_tag_key]}
                    },
                },
            }

            # Create ASG tagging event rule
            asg_rule_name = self._get_asg_rule_name()
            events_client.put_rule(
                Name=asg_rule_name,
                EventPattern=json.dumps(asg_tagging_event_pattern),
                State="ENABLED",
            )
            events_client.put_targets(
                Rule=asg_rule_name,
                Targets=[
                    {
                        "Id": "1",
                        "Arn": self._env.tagging_event_bus_arn,
                        "RoleArn": self._env.tagging_event_rule_role_arn,
                    }
                ],
            )

            # Create tagging event rule
            tagging_rule_name = self._get_resource_rule_name()

            resource_tagging_event_pattern: Mapping[str, Any] = {
                "source": ["aws.tag"],
                "detail": {"changed-tag-keys": [self._env.schedule_tag_key]},
            }

            events_client.put_rule(
                Name=tagging_rule_name,
                EventPattern=json.dumps(resource_tagging_event_pattern),
                State="ENABLED",
            )
            events_client.put_targets(
                Rule=tagging_rule_name,
                Targets=[
                    {
                        "Id": "1",
                        "Arn": self._env.tagging_event_bus_arn,
                        "RoleArn": self._env.tagging_event_rule_role_arn,
                    }
                ],
            )
            self._create_regional_event_bus(events_client)
        except ClientError as error:
            self._logger.error(f"Error in creating rule error {error}")
            raise error
        except Exception as error:
            self._logger.error(f"Error in creating rule error {error}")
            raise error
        return True

    def _delete_event_rule(self, events_client: EventBridgeClient) -> None:
        # Delete ASG tagging event rule
        asg_rule_name = self._get_asg_rule_name()
        events_client.remove_targets(Rule=asg_rule_name, Ids=["1"])
        events_client.delete_rule(Name=asg_rule_name)

        # Delete tagging event rule
        tagging_rule_name = self._get_resource_rule_name()
        events_client.remove_targets(Rule=tagging_rule_name, Ids=["1"])
        events_client.delete_rule(Name=tagging_rule_name)

        # delete event bus
        self._delete_regional_event_bus(events_client)

    def _create_event_rules(self, regions: List[str]) -> CustomResourceResponse:
        success_regions_for_rollback = []
        assumed_role = lambda_execution_role()
        for region in regions:
            try:
                events_client = assumed_role.client("events", region)
                response = self._create_event_rule(events_client)
                if response:
                    success_regions_for_rollback.append(region)
            except Exception as error:
                self._logger.error(
                    f"Failed to create event rules in region {region}: {error}"
                )
                for rollback_region in success_regions_for_rollback:
                    events_client = assumed_role.client("events", rollback_region)
                    self._delete_event_rule(events_client)
                raise error

        return self.OkResponse(
            data={"REGIONAL_BUS_NAME": self._env.regional_event_bus_name}
        )

    def _delete_event_rules(self, regions: List[str]) -> None:
        assumed_role = lambda_execution_role()
        for region in regions:
            try:
                events_client = assumed_role.client("events", region)
                self._delete_event_rule(events_client)
            except Exception as e:
                self._logger.error(
                    f"Failed to delete event rules in region {region}: {e}"
                )
                # Continue with other regions even if one fails during cleanup

    def _create_request(self) -> CustomResourceResponse:
        regions = self.purge_empty_strings(self.resource_properties, "regions")
        if regions:
            return self._create_event_rules(regions)
        else:
            regions.append(lambda_execution_role().region)
            return self._create_event_rules(regions)

    def _update_request(self) -> CustomResourceResponse:
        current_regions = self.purge_empty_strings(self.resource_properties, "regions")
        if not current_regions:
            current_regions.append(lambda_execution_role().region)

        old_regions = self.purge_empty_strings(self.old_resource_properties, "regions")
        if not old_regions:
            old_regions.append(lambda_execution_role().region)

        self._delete_event_rules(old_regions)
        try:
            return self._create_event_rules(current_regions)
        except ClientError as error:
            self._logger.error(
                f"Failed to create event rules in regions {current_regions}: {error}"
            )
            return self.ErrorResponse(reason=f"Failed to create event rules: {error}")
        except Exception as error:
            self._logger.error(
                f"Unexpected error creating event rules in regions {current_regions}: {error}"
            )
            return self.ErrorResponse(reason=f"Unexpected error: {error}")

    def _delete_request(self) -> CustomResourceResponse:
        regions = self.purge_empty_strings(self.resource_properties, "regions")

        if not regions:
            regions.append(lambda_execution_role().region)
        try:
            self._delete_event_rules(regions)
        except Exception as error:
            self._logger.warning(
                f"Error during delete request for regions {regions}: {error}"
            )
            # Continue with success for delete operations to avoid stuck resources
        return self.OkResponse(
            data={"REGIONAL_BUS_NAME": self._env.regional_event_bus_name}
        )
