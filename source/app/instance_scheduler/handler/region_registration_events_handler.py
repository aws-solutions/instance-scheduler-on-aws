# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import json
from enum import Enum
from functools import cached_property
from typing import TYPE_CHECKING, Any, Final, List, Mapping, TypedDict

from aws_lambda_powertools import Logger
from instance_scheduler.handler.environments.region_registration_environment import (
    RegionRegistrationEnvironment,
)
from instance_scheduler.handler.service.ssm import SSMService
from instance_scheduler.observability.powertools_logging import (
    powertools_logger,
    should_log_events,
)
from instance_scheduler.util.custom_resource_waiter import (
    CustomResourceWaiter,
    CustomResourceWaiterResponse,
)
from instance_scheduler.util.session_manager import (
    AssumedRole,
    assume_role,
    lambda_execution_role,
)
from urllib3 import PoolManager

if TYPE_CHECKING:
    from aws_lambda_powertools.utilities.typing import LambdaContext
    from mypy_boto3_lambda.client import LambdaClient
else:
    LambdaContext = object
    LambdaClient = object

http = PoolManager()

logger: Final = powertools_logger()


class RegionRegistrationState(Enum):
    CREATED = "created"
    REQUESTED = "requested"
    REGISTERING = "registering"
    MANAGED = "managed"
    DELETING = "deleting"
    DELETED = "deleted"
    ERROR = "error"
    UNKNOWN = "unknown"


@logger.inject_lambda_context(log_event=should_log_events(logger))
def lambda_handler(event: Mapping[str, Any], context: LambdaContext) -> None:

    try:
        env = RegionRegistrationEnvironment.from_env()
        handler = RegionRegistrationHandler(event, context, logger, env)
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


class RegionRegistrationProperties(TypedDict):
    regions: List[str]


class RegionRegistrationHandler(CustomResourceWaiter[RegionRegistrationProperties]):
    def __init__(
        self,
        event: Any,
        context: LambdaContext,
        logger: Logger,
        env: RegionRegistrationEnvironment,
    ) -> None:
        super().__init__(event, context)
        self._logger: Final = logger
        self._env: Final = env

    @cached_property
    def _hub_lambda_client(self) -> LambdaClient:
        if self._env.hub_account_id != lambda_execution_role().account:
            assumed_role: AssumedRole = assume_role(
                account=self._env.hub_account_id,
                region=lambda_execution_role().region,
                role_name=self._env.hub_registration_role_name,
            )
        else:
            assumed_role = lambda_execution_role()
        lambda_client: LambdaClient = assumed_role.client("lambda")
        return lambda_client

    def _put_ssm_parameter_for_region(
        self,
        region: str,
        ssm_param_state: RegionRegistrationState,
    ) -> None:
        ssm_service: SSMService = SSMService()
        ssm_service.put_parameter(
            name=f"{self._env.ssm_param_path}/{region}",
            value=ssm_param_state.value,
        )

    def _send_registration_request(
        self, payload: Mapping[str, Any], lambda_client: LambdaClient
    ) -> None:
        lambda_client.invoke(
            FunctionName=self._env.hub_registration_function_arn,
            InvocationType="Event",
            Payload=json.dumps(payload).encode(),
        )

    def _create_request(self) -> CustomResourceWaiterResponse:
        regions = self.purge_empty_strings(self.resource_properties, "regions")
        lambda_client = self._hub_lambda_client

        if not regions:
            regions = [lambda_execution_role().region]

        account_id = lambda_execution_role().account

        for region in regions:
            payload = {"account": account_id, "region": region, "operation": "Register"}
            self._put_ssm_parameter_for_region(
                region,
                ssm_param_state=RegionRegistrationState.CREATED,
            )
            self._send_registration_request(payload, lambda_client)
        return self.OkResponse(is_complete=False)

    def _update_request(self) -> CustomResourceWaiterResponse:
        lambda_client = self._hub_lambda_client
        current_regions = self.purge_empty_strings(self.resource_properties, "regions")
        if not current_regions:
            current_regions.append(lambda_execution_role().region)

        old_regions = self.purge_empty_strings(self.old_resource_properties, "regions")
        if not old_regions:
            old_regions.append(lambda_execution_role().region)

        delete_regions = list(set(old_regions) - set(current_regions))
        account_id = lambda_execution_role().account
        for region in delete_regions:
            payload = {
                "account": account_id,
                "region": region,
                "operation": "Deregister",
            }
            self._put_ssm_parameter_for_region(
                region,
                ssm_param_state=RegionRegistrationState.DELETING,
            )
            self._send_registration_request(payload, lambda_client)
        new_regions = list(set(current_regions) - set(old_regions))
        for region in new_regions:
            payload = {
                "account": account_id,
                "region": region,
                "operation": "Register",
            }
            self._put_ssm_parameter_for_region(
                region,
                ssm_param_state=RegionRegistrationState.CREATED,
            )
            self._send_registration_request(payload, lambda_client)
        return self.OkResponse(is_complete=False)

    def _delete_request(self) -> CustomResourceWaiterResponse:
        regions = self.purge_empty_strings(self.resource_properties, "regions")
        lambda_client = self._hub_lambda_client
        if not regions:
            regions = [lambda_execution_role().region]
        account_id = lambda_execution_role().account
        for region in regions:
            payload = {
                "account": account_id,
                "region": region,
                "operation": "Deregister",
            }
            self._put_ssm_parameter_for_region(
                region,
                ssm_param_state=RegionRegistrationState.DELETING,
            )
            self._send_registration_request(payload, lambda_client)
        return self.OkResponse(is_complete=False)
