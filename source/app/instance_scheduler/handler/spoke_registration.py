# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import json
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, TypeGuard

from instance_scheduler.handler.base import Handler
from instance_scheduler.util.app_env import get_app_env
from instance_scheduler.util.dynamodb_utils import DynamoDBUtils
from instance_scheduler.util.logger import Logger

if TYPE_CHECKING:
    from aws_lambda_powertools.utilities.typing import LambdaContext
else:
    LambdaContext = object


INF_HANDLER = "Request Handler {} : Received request {} at {}"
EVENT_BUS_NAMESPACE_PREFIX = "/scheduler/do-not-delete-manually/{}"
EVENT_CREATE = "Create"
EVENT_DELETE = "Delete"

SpokeRegistrationRequest = dict[str, Any]


class SpokeRegistrationHandler(Handler[SpokeRegistrationRequest]):
    """
    Handles event from cloudwatch rule time
    """

    def __init__(self, event: SpokeRegistrationRequest, context: LambdaContext) -> None:
        self._context = context
        self._event = event
        self._configuration = None
        self._lambda_client = None

        logging_stream_name = "-".join(["eventbus_request_handler"])
        dt = datetime.now(timezone.utc)
        app_env = get_app_env()
        self._config_table_name = app_env.config_table_name
        log_stream = "{}-{:0>4d}{:0>2d}{:0>2d}".format(
            logging_stream_name, dt.year, dt.month, dt.day
        )
        self._logger = Logger(
            log_group=app_env.log_group,
            log_stream=log_stream,
            topic_arn=app_env.topic_arn,
            debug=app_env.enable_debug_logging,
        )

    @staticmethod
    def is_handling_request(
        event: Mapping[str, Any]
    ) -> TypeGuard[SpokeRegistrationRequest]:
        """
        Handler for EventBus request to update accounts.
        :return: True
        """
        return str(event.get("detail-type", "")) == "Parameter Store Change"

    def handle_request(self) -> str:
        """
        Handles the CloudWatch Rule timer events
        :return:
        """
        try:
            self._logger.info(
                INF_HANDLER,
                self.__class__.__name__,
                json.dumps(self._event),
                datetime.now(),
            )
            detail = self._event.get("detail", None)
            if detail is not None:
                self._logger.debug(f"Details of the event {detail}")
                dynamodb_table = DynamoDBUtils.get_dynamodb_table_resource_ref(
                    self._config_table_name
                )
                config_key = {"name": "scheduler", "type": "config"}
                if detail.get("operation") == EVENT_CREATE:
                    self._logger.info("Add account id from the config")
                    account = self._event.get("account")
                    update_account_ids_response = dynamodb_table.update_item(
                        TableName=self._config_table_name,
                        Key=config_key,
                        UpdateExpression="add remote_account_ids :a",
                        ExpressionAttributeValues={":a": set({account})},
                        ReturnValues="UPDATED_NEW",
                    )
                    self._logger.debug(
                        f"Response from account update: {update_account_ids_response}"
                    )
                elif detail.get("operation") == EVENT_DELETE:
                    account = self._event.get("account")
                    self._logger.info(f"remove account {account} from the config")
                    update_account_ids_response = dynamodb_table.update_item(
                        TableName=self._config_table_name,
                        Key=config_key,
                        UpdateExpression="delete remote_account_ids :a",
                        ExpressionAttributeValues={":a": set({account})},
                        ReturnValues="UPDATED_NEW",
                    )
                    self._logger.debug(
                        f"Response from account update: {update_account_ids_response}"
                    )
                else:
                    self._logger.info(
                        f"event details.operations doesn't match the scenarios configured. {detail}"
                    )
            return "Exiting event bus request handler"
        except Exception as error:
            self._logger.error(str(error))
            return "Error in event bus request handler."
        finally:
            self._logger.flush()
