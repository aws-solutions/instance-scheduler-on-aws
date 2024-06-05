# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import json
from functools import cached_property
from typing import TYPE_CHECKING, Any, Final, Mapping, TypedDict

import boto3
from aws_lambda_powertools import Logger
from botocore.exceptions import ClientError
from urllib3 import PoolManager

from instance_scheduler.handler.environments.remote_registration_environment import (
    RemoteRegistrationEnvironment,
)
from instance_scheduler.util import get_boto_config
from instance_scheduler.util.custom_resource import (
    CustomResource,
    CustomResourceResponse,
)

if TYPE_CHECKING:
    from aws_lambda_powertools.utilities.typing import LambdaContext
    from mypy_boto3_lambda import LambdaClient
else:
    LambdaContext = object
    LambdaClient = object

http = PoolManager()


def handle_remote_registration_request(
    event: Mapping[str, Any], context: LambdaContext
) -> None:
    # this lambda exists in the spoke stack and does not require the SnsHandler
    logger = Logger(log_uncaught_exceptions=True, use_rfc3339=True)
    try:
        env = RemoteRegistrationEnvironment.from_env()
        handler = RemoteRegistrationCustomResourceHandler(event, context, logger, env)
        handler.handle_request()
    except Exception:
        logger.error("Error occurred while running custom resource lambda")
        response_body = {
            "Status": "FAILED",
            "Reason": "Response sent to cloudformation to prevent hung resource",
            "PhysicalResourceId": event.get("LogicalResourceId"),
            "StackId": event.get("StackId"),
            "RequestId": event.get("RequestId"),
            "LogicalResourceId": event.get("LogicalResourceId"),
        }

        headers = {"Content-Type": "application/json"}
        http.request(  # type: ignore[no-untyped-call]
            "PUT",
            event.get("ResponseURL"),
            headers=headers,
            body=json.dumps(response_body),
        )


class RemoteRegistrationProperties(TypedDict):
    pass


class RemoteRegistrationCustomResourceHandler(
    CustomResource[RemoteRegistrationProperties]
):
    """
    Implements handler for remote registration custom resource
    """

    def __init__(
        self,
        event: Any,
        context: LambdaContext,
        logger: Logger,
        env: RemoteRegistrationEnvironment,
    ) -> None:
        super().__init__(event, context)
        self._env: Final = env
        self._logger: Final = logger
        self._spoke_account_id: Final = context.invoked_function_arn.split(":")[4]

    @cached_property
    def _lambda_client(self) -> LambdaClient:
        client: LambdaClient = boto3.client("lambda", config=get_boto_config())
        return client

    # handles Create request from CloudFormation
    def _create_request(self) -> CustomResourceResponse:
        try:
            payload = str.encode(
                json.dumps({"account": self._spoke_account_id, "operation": "Register"})
            )
            self._lambda_client.invoke(
                FunctionName=self._env.hub_registration_lambda_arn,
                InvocationType="RequestResponse",
                LogType="None",
                Payload=payload,
            )
            self._logger.info(
                f"Registered spoke account {self._spoke_account_id} with hub account registration lambda {self._env.hub_registration_lambda_arn}"
            )
            return self.OkResponse()
        except ClientError:
            message = f"Unable to register with hub account via registration lambda: {self._env.hub_registration_lambda_arn}"
            self._logger.error(message)
            return self.ErrorResponse(reason=message)

    # handles Update request from CloudFormation
    def _update_request(self) -> CustomResourceResponse:
        return self.OkResponse(reason="No handler for Update request")

    # handles Delete request from CloudFormation
    def _delete_request(self) -> CustomResourceResponse:
        try:
            payload = str.encode(
                json.dumps(
                    {"account": self._spoke_account_id, "operation": "Deregister"}
                )
            )
            self._lambda_client.invoke(
                FunctionName=self._env.hub_registration_lambda_arn,
                InvocationType="RequestResponse",
                LogType="None",
                Payload=payload,
            )
            self._logger.info(
                f"Deregistered spoke account {self._spoke_account_id} with hub account registration lambda {self._env.hub_registration_lambda_arn}"
            )
            return self.OkResponse()
        except ClientError:
            message = f"Unable to deregister with hub account via registration lambda: {self._env.hub_registration_lambda_arn}"
            self._logger.error(message)
            return self.ErrorResponse(reason=message)
