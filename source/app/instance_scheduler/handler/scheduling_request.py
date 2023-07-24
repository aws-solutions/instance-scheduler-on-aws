# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import dataclasses
import json
from collections.abc import Mapping
from datetime import datetime
from typing import TYPE_CHECKING, Any, Final, Literal, Optional, TypedDict, TypeGuard

import boto3
from boto3 import Session
from botocore.exceptions import ClientError

from instance_scheduler import configuration
from instance_scheduler.configuration import scheduling_context
from instance_scheduler.handler.base import Handler
from instance_scheduler.schedulers.instance_scheduler import InstanceScheduler
from instance_scheduler.schedulers.instance_states import InstanceStates
from instance_scheduler.service import ServiceArgs, services
from instance_scheduler.util import get_boto_config
from instance_scheduler.util.app_env import get_app_env
from instance_scheduler.util.logger import Logger

if TYPE_CHECKING:
    from aws_lambda_powertools.utilities.typing import LambdaContext
    from mypy_boto3_lambda.client import LambdaClient
    from mypy_boto3_sts.client import STSClient
else:
    LambdaContext = object
    LambdaClient = object
    STSClient = object


class SchedulerRequest(TypedDict):
    action: Literal["scheduler:run"]
    configuration: dict[str, Any]
    dispatch_time: str


class SchedulingRequestHandler(Handler[SchedulerRequest]):
    def __init__(self, event: SchedulerRequest, context: LambdaContext) -> None:
        self._function_name: Final = context.function_name
        self._hub_account_id: Final = context.invoked_function_arn.split(":")[4]
        self._scheduling_context = scheduling_context.from_dict(event["configuration"])
        self._target_account_id: Final = (
            self._hub_account_id
            if self._scheduling_context.schedule_lambda_account
            else self._scheduling_context.account_id
        )

        self._sts_client: Optional[STSClient] = None
        self._lambda_client: Optional[LambdaClient] = None

        app_env: Final = get_app_env()

        self._state_table_name: Final = app_env.state_table_name
        self._stack_name: Final = app_env.stack_name

        log_stream_name: Final = "-".join(
            [
                "Scheduler",
                self._scheduling_context.service,
                self._target_account_id,
                self._scheduling_context.region,
            ]
        )
        dt: Final = datetime.now(self._scheduling_context.default_timezone)
        log_stream: Final = "{}-{:0>4d}{:0>2d}{:0>2d}".format(
            log_stream_name, dt.year, dt.month, dt.day
        )
        self._logger: Final = Logger(
            log_group=app_env.log_group,
            log_stream=log_stream,
            topic_arn=app_env.topic_arn,
            debug=app_env.enable_debug_logging,
        )

        if self._scheduling_context.schedules == {}:
            # for large configurations the schedules are not passed in the event, so we
            # need to reload them from dynamo
            global_config = configuration.get_global_configuration(self._logger)
            self._scheduling_context = dataclasses.replace(
                self._scheduling_context, schedules=global_config.schedules
            )

    @staticmethod
    def is_handling_request(event: Mapping[str, Any]) -> TypeGuard[SchedulerRequest]:
        return str(event.get("action", "")) == "scheduler:run"

    def handle_request(self) -> Any:
        with self._logger:
            message: Final = (
                "Handler {} scheduling request for service {}, account {}, region {} "
                "at {}, time stamp is based on the default timezone selected for the "
                "solution."
            )
            self._logger.info(
                message.format(
                    self.__class__.__name__,
                    self._scheduling_context.service,
                    self._target_account_id,
                    self._scheduling_context.region,
                    datetime.now(self._scheduling_context.default_timezone),
                )
            )

            service_args: Final = ServiceArgs(
                account_id=self._target_account_id,
                logger=self._logger,
                stack_name=self._stack_name,
                session=self.get_session_for_target_account(),
                scheduling_context=self._scheduling_context,
            )

            service_name: Final = self._scheduling_context.service

            service_strategy: Final = services[service_name](service_args)

            instance_states: Final = InstanceStates(
                self._state_table_name, service_name, self._logger
            )

            scheduler: Final = InstanceScheduler(
                service_strategy,
                self._scheduling_context,
                instance_states,
                self._target_account_id,
                self.get_role_arn(),
                self._logger,
            )

            result: Final = {self._target_account_id: scheduler.run()}

            self._logger.info("Scheduler result {}", result)

        return result

    @property
    def sts(self) -> STSClient:
        if self._sts_client is None:
            session: Final = Session()
            sts_regional_endpoint: Final = str.format(
                "https://sts.{}.amazonaws.com", session.region_name
            )
            # STS client __must__ use a regional endpoint so that tokens are version 2.
            # version 1 tokens are not valid in opt-in regions unless enabled on an
            # account level
            self._sts_client = session.client(
                "sts",
                region_name=session.region_name,
                endpoint_url=sts_regional_endpoint,
                config=get_boto_config(),
            )
        return self._sts_client

    def targeting_hub_account(self) -> bool:
        return self._target_account_id == self._hub_account_id

    def get_session_for_target_account(self) -> Session:
        if self.targeting_hub_account():
            return Session(region_name=self._scheduling_context.region)
        else:
            return self.get_session_for_spoke_account()

    def get_role_arn(self) -> Optional[str]:
        if self.targeting_hub_account():
            # no role in the hub account
            return None
        else:
            spoke_account_role_name: Final = "-".join(
                [
                    self._scheduling_context.namespace,
                    self._scheduling_context.scheduler_role_name,
                ]
            )
            return ":".join(
                [
                    "arn",
                    self._scheduling_context.aws_partition,
                    "iam",
                    "",
                    self._target_account_id,
                    f"role/{spoke_account_role_name}",
                ]
            )

    def get_session_for_spoke_account(self) -> Session:
        spoke_account_role_arn: Final = self.get_role_arn()
        if not spoke_account_role_arn:
            raise ValueError("No role to assume")

        # get a token for the cross account role and use it to create a session
        try:
            session_name: Final = "{}-scheduler-{}".format(
                self._scheduling_context.service, self._target_account_id
            )
            # assume a role
            token: Final = self.sts.assume_role(
                RoleArn=spoke_account_role_arn, RoleSessionName=session_name
            )
            credentials: Final = token["Credentials"]
            # create a session using the assumed role credentials
            return Session(
                aws_access_key_id=credentials["AccessKeyId"],
                aws_secret_access_key=credentials["SecretAccessKey"],
                aws_session_token=credentials["SessionToken"],
                region_name=self._scheduling_context.region,
            )
        except ClientError as ex:
            self._logger.error(
                "Error Code {}".format(ex.response.get("Error", {}).get("Code"))
            )
            if ex.response.get("Error", {}).get("Code") == "AccessDenied":
                self.remove_account_from_config(
                    aws_account=self._target_account_id,
                    cross_account_role=spoke_account_role_arn,
                )
            else:
                self._logger.error(
                    "Can not assume role {} for account {}, ({}))".format(
                        spoke_account_role_arn, self._target_account_id, str(ex)
                    )
                )
            raise RuntimeError(
                "Unable to assume role {} for account {}".format(
                    spoke_account_role_arn, self._target_account_id
                )
            )

    @property
    def lambda_client(self) -> LambdaClient:
        if self._lambda_client is None:
            self._lambda_client = boto3.client("lambda", config=get_boto_config())
        return self._lambda_client

    def remove_account_from_config(
        self, aws_account: str, cross_account_role: str
    ) -> None:
        """
        This method will invoke the lambda to remove the aws_account from the
        configuration, it calls the lambda handler eventbus_request_handler, and sends
        payload which will update the config by removing the account from further
        scheduling.
        {
            "account": 111122223333,
            "detail-type": "Parameter Store Change",
            "detail": {
                "operation": "Delete"
            }
        }
        :param aws_account: account where the assume role permission is not available
        for the lambda role to assume.
        :param cross_account_role: role name for logging message to SNS.
        """
        try:
            message: Final = (
                "Removing the account {} from scheduling configuration as assume role "
                "permission is missing for the iam role {}"
            )
            self._logger.error(message.format(aws_account, cross_account_role))
            payload: Final = str.encode(
                json.dumps(
                    {
                        "account": aws_account,
                        "detail-type": "Parameter Store Change",
                        "detail": {"operation": "Delete"},
                    }
                )
            )
            response: Final = self.lambda_client.invoke(
                FunctionName=self._function_name,
                InvocationType="Event",
                LogType="None",
                Payload=payload,
            )
            self._logger.info(
                "Removing account {} from configuration".format(aws_account)
            )
            self._logger.debug(
                "Lambda response {} for removing account from configuration".format(
                    response
                )
            )
        except Exception as ex:
            self._logger.error(
                "Error invoking lambda {} error {}".format(self._function_name, ex)
            )
