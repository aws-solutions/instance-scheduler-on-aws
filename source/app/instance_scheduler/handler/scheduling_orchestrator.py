# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import json
from collections.abc import Iterator, Mapping
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Literal, Optional, TypedDict, TypeGuard

import boto3

from instance_scheduler import configuration
from instance_scheduler.boto_retry import get_client_with_standard_retry
from instance_scheduler.configuration.scheduler_config import GlobalConfig
from instance_scheduler.configuration.scheduling_context import SchedulingContext
from instance_scheduler.handler.base import Handler
from instance_scheduler.ops_metrics.metric_type.deployment_description_metric import (
    DeploymentDescriptionMetric,
)
from instance_scheduler.ops_metrics.metrics import collect_metric
from instance_scheduler.util.app_env import get_app_env
from instance_scheduler.util.logger import Logger

if TYPE_CHECKING:
    from aws_lambda_powertools.utilities.typing import LambdaContext
else:
    LambdaContext = object
    STSClient = object

LOG_STREAM = "{}-{:0>4d}{:0>2d}{:0>2d}"
LOG_STREAM_PREFIX = "Scheduler"


class OrchestrationRequest(TypedDict):
    scheduled_action: Literal["run_orchestrator"]


LAMBDA_PAYLOAD_CAPACITY_BYTES = (
    200_000  # is actually 256_000 but this provides some overhead
)


class SchedulingOrchestratorHandler(Handler[OrchestrationRequest]):
    """
    Handles event from cloudwatch rule timer
    """

    def __init__(self, event: OrchestrationRequest, context: LambdaContext) -> None:
        self._context = context
        self._event = event
        self._configuration: Optional[GlobalConfig] = None
        self._lambda_client = None
        self._hub_account_id: str = context.invoked_function_arn.split(":")[4]

        # Setup logging
        classname = self.__class__.__name__
        app_env = get_app_env()
        dt = datetime.now(timezone.utc)
        logstream = LOG_STREAM.format(classname, dt.year, dt.month, dt.day)
        self._logger = Logger(
            log_group=app_env.log_group,
            log_stream=logstream,
            topic_arn=app_env.topic_arn,
            debug=app_env.enable_debug_logging,
        )

    @property
    def lambda_client(self) -> Any:
        """
        Get the lambda client
        :return: lambda client
        """
        if self._lambda_client is None:
            self._lambda_client = get_client_with_standard_retry("lambda")
        return self._lambda_client

    @property
    def configuration(self) -> GlobalConfig:
        """
        Returns the scheduler configuration
        :return: scheduler configuration
        """
        if self._configuration is None:
            self._configuration = configuration.get_global_configuration(self._logger)
        return self._configuration

    def accounts_and_roles(self, config: GlobalConfig) -> Iterator[str]:
        """
        Iterates account and cross-account-roles of the accounts to operate on
        :return:
        """
        processed_accounts = []

        if config.schedule_lambda_account:
            processed_accounts.append(self._hub_account_id)
            yield self._hub_account_id

        for remote_account in config.remote_account_ids:
            if remote_account is None:
                continue
            # warn and skip if account was already processed
            if remote_account in processed_accounts:
                self._logger.warning(
                    "Remote account {} is already processed", remote_account
                )
                continue
            yield remote_account

    def target_account_id(self, context: SchedulingContext) -> str:
        """
        Iterates list of accounts to process
        :param context:
        :return:
        """
        if context.schedule_lambda_account:
            return self._hub_account_id
        else:
            return context.account_id

    @staticmethod
    def is_handling_request(
        event: Mapping[str, Any]
    ) -> TypeGuard[OrchestrationRequest]:
        """
        Handler for cloudwatch event to run the scheduler
        :return: True
        """
        return str(event.get("scheduled_action", "")) == "run_orchestrator"

    def handle_request(self) -> list[Any]:
        """
        Handles the CloudWatch Rule timer events
        :return:
        """
        try:
            self._logger.info(
                "Handler {} : Received request {} at {}",
                self.__class__.__name__,
                json.dumps(self._event),
                datetime.now(),
            )

            result = []
            for scheduling_context in self.list_scheduling_contexts(self.configuration):
                result.append(self._run_scheduling_lambda(scheduling_context))

            collect_metric(
                DeploymentDescriptionMetric(
                    services=self.configuration.scheduled_services,
                    regions=self.configuration.regions,
                    num_accounts=sum(
                        1 for _ in self.accounts_and_roles(self.configuration)
                    ),
                ),
                logger=self._logger,
            )

            return result
        finally:
            self._logger.flush()

    def list_scheduling_contexts(
        self, config: GlobalConfig
    ) -> Iterator[SchedulingContext]:
        services = config.scheduled_services
        regions = config.regions
        current_dt = datetime.now(timezone.utc)
        if not regions:
            regions = [boto3.Session().region_name]
            # todo: better way to use local region?
            # todo: could pull from event the same as how lambda_account is fetched

        for service in services:
            for region in regions:
                for account in self.accounts_and_roles(
                    config
                ):  # todo: pull from config.remote_accounts directly?
                    if account is self._hub_account_id:  # local account
                        schedule_lambda_account = True
                        account_id = ""
                    else:  # remote account
                        schedule_lambda_account = False
                        account_id = account

                    yield SchedulingContext(
                        account_id=account_id,  # mutated above
                        service=service,
                        region=region,
                        current_dt=current_dt,
                        schedules=config.schedules,
                        default_timezone=config.default_timezone,
                        schedule_clusters=config.schedule_clusters,
                        tag_name=config.tag_name,
                        trace=config.trace,
                        enable_ssm_maintenance_windows=config.enable_ssm_maintenance_windows,
                        use_metrics=config.use_metrics,
                        namespace=config.namespace,
                        aws_partition=config.aws_partition,
                        scheduler_role_name=config.scheduler_role_name,
                        organization_id=config.organization_id,
                        schedule_lambda_account=schedule_lambda_account,  # mutated above
                        create_rds_snapshot=config.create_rds_snapshot,
                        started_tags=config.started_tags,  #
                        stopped_tags=config.stopped_tags,
                    )

    def _run_scheduling_lambda(self, context: SchedulingContext) -> dict[str, Any]:
        # runs a service/account/region subset of the configuration as a new lambda function
        self._logger.info(
            "Starting lambda function for scheduling {} instances for account {} in region {}",
            context.service,
            self.target_account_id(context),
            context.region,
        )

        # need to convert configuration to dictionary to allow it to be passed in event
        event_payload = context.to_dict()

        payload = str.encode(
            json.dumps(
                {
                    "action": "scheduler:run",
                    "configuration": event_payload,
                    "dispatch_time": str(datetime.now()),
                }
            )
        )

        if len(payload) > LAMBDA_PAYLOAD_CAPACITY_BYTES:
            strip_schedules_and_periods(event_payload)
            payload = str.encode(
                json.dumps(
                    {
                        "action": "scheduler:run",
                        "configuration": event_payload,
                        "dispatch_time": str(datetime.now()),
                    }
                )
            )

        # start the lambda function
        resp = self.lambda_client.invoke(
            FunctionName=self._context.function_name,
            InvocationType="Event",
            LogType="None",
            Payload=payload,
        )
        if resp["StatusCode"] != 202:
            self._logger.error(
                "Error executing {}, version {} with configuration {}",
                self._context.function_name,
                self._context.function_version,
                event_payload,
            )

        result = {
            "service": context.service,
            "account": self.target_account_id(context),
            "region": context.region,
            "lambda_invoke_result": resp["StatusCode"],
            "lambda_request_id": resp["ResponseMetadata"]["RequestId"],
        }
        return result


def strip_schedules_and_periods(event_dict: dict[str, Any]) -> None:
    event_dict["schedules"] = {}
    event_dict["periods"] = {}
