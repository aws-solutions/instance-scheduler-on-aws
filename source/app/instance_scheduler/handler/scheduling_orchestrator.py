# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import json
import traceback
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import (
    TYPE_CHECKING,
    Any,
    Final,
    Literal,
    TypedDict,
    TypeGuard,
    cast,
)

from aws_lambda_powertools import Logger
from instance_scheduler.handler.environments.orchestrator_environment import (
    OrchestratorEnvironment,
)
from instance_scheduler.handler.scheduling_request import SchedulingRequest
from instance_scheduler.model.period_definition import (
    InvalidPeriodDefinition,
    PeriodDefinition,
)
from instance_scheduler.model.schedule_definition import (
    InvalidScheduleDefinition,
    ScheduleDefinition,
)
from instance_scheduler.model.store.dynamo_period_definition_store import (
    DynamoPeriodDefinitionStore,
)
from instance_scheduler.model.store.dynamo_resource_registry import (
    DynamoResourceRegistry,
)
from instance_scheduler.model.store.dynamo_schedule_definition_store import (
    DynamoScheduleDefinitionStore,
)
from instance_scheduler.model.store.in_memory_period_definition_store import (
    InMemoryPeriodDefinitionStore,
)
from instance_scheduler.model.store.in_memory_schedule_definition_store import (
    InMemoryScheduleDefinitionStore,
)
from instance_scheduler.model.store.resource_registry import ResourceRegistry
from instance_scheduler.observability.powertools_logging import (
    powertools_logger,
    should_log_events,
)
from instance_scheduler.util import safe_json
from instance_scheduler.util.session_manager import lambda_execution_role
from instance_scheduler.util.validation import ValidationException, validate_string

if TYPE_CHECKING:
    from aws_lambda_powertools.utilities.typing import LambdaContext
else:
    LambdaContext = object

logger: Final = powertools_logger()


LAMBDA_PAYLOAD_CAPACITY_BYTES = (
    200_000  # is actually 256_000 but this provides some overhead
)


class OrchestrationRequest(TypedDict):
    scheduled_action: Literal["run_orchestrator"]


def validate_orchestration_request(
    untyped_dict: Mapping[str, Any],
) -> TypeGuard[OrchestrationRequest]:
    validate_string(untyped_dict, "scheduled_action", required=True)

    if untyped_dict["scheduled_action"] != "run_orchestrator":
        raise ValidationException(
            f"unknown scheduled_action. received '{untyped_dict['scheduled_action']}', expected 'run_orchestrator'"
        )

    return True


@logger.inject_lambda_context(log_event=should_log_events(logger))
def lambda_handler(event: Mapping[str, Any], context: LambdaContext) -> Any:
    env: Final = OrchestratorEnvironment.from_env()

    try:
        validate_orchestration_request(event)
        event = cast(OrchestrationRequest, event)
        handler = SchedulingOrchestratorHandler(event, context, env, logger)
        return handler.handle_request()
    except Exception as e:
        logger.error(
            f"Error handling orchestration registration request {safe_json(event)}: ({e})\n{traceback.format_exc()}"
        )
        raise e


class SchedulingOrchestratorHandler:
    """
    Handles event from cloudwatch rule timer
    """

    registry: Final[ResourceRegistry]

    def __init__(
        self,
        event: OrchestrationRequest,
        context: LambdaContext,
        env: OrchestratorEnvironment,
        logger: Logger,
    ) -> None:
        self._env = env
        self._context = context
        self._event = event
        self._logger = logger
        self._lambda_client = None
        self._hub_account_id: str = context.invoked_function_arn.split(":")[4]
        self.registry = DynamoResourceRegistry(env.registry_table)

    @property
    def lambda_client(self) -> Any:
        """
        Get the lambda client
        :return: lambda client
        """
        if self._lambda_client is None:
            self._lambda_client = lambda_execution_role().client("lambda")
        return self._lambda_client

    def handle_request(self) -> list[Any]:
        """
        Handles the CloudWatch Rule timer events
        :return:
        """
        self._logger.info(
            f"Handler {self.__class__.__name__} : Received request {json.dumps(self._event)} at {datetime.now()}"
        )

        result = []

        cached_schedules, cached_periods = prefetch_schedules_and_periods(
            self._env, self._logger
        )
        for target in self.registry.list_all_by_scheduling_target():
            target_schedules = InMemoryScheduleDefinitionStore()
            target_periods = InMemoryPeriodDefinitionStore()

            # pre-load schedules/periods for the target
            for resource in target.resources:
                schedule = cached_schedules.find_by_name(resource.schedule)
                if schedule is None:
                    continue

                target_schedules.put(schedule, overwrite=True)
                for period in schedule.fetch_period_definitions(cached_periods):
                    target_periods.put(period, overwrite=True)

            current_dt_str = datetime.now(timezone.utc).isoformat()
            scheduler_request = SchedulingRequest(
                action="scheduler:run",
                account=target.account,
                region=target.region,
                service=target.service,
                current_dt=current_dt_str,
                dispatch_time=datetime.now(timezone.utc).isoformat(),
                schedules=target_schedules.serialize(),
                periods=target_periods.serialize(),
            )
            result.append(self._run_scheduling_lambda(scheduler_request))

        if not result:
            self._logger.info("No resources registered to schedule")

        return result

    def _run_scheduling_lambda(
        self, scheduler_request: SchedulingRequest
    ) -> dict[str, Any]:
        # runs a service/account/region subset of the configuration as a new lambda function
        self._logger.info(
            f'Starting lambda function for scheduling {scheduler_request["service"]} instances for account {scheduler_request["account"]} in region {scheduler_request["region"]}'
        )

        payload = str.encode(json.dumps(scheduler_request))
        if len(payload) > LAMBDA_PAYLOAD_CAPACITY_BYTES:
            # strip periods and let the request handler reload them
            del scheduler_request["periods"]
            payload = str.encode(json.dumps(scheduler_request))
        if len(payload) > LAMBDA_PAYLOAD_CAPACITY_BYTES:
            # if payload is still too large, strip schedules as well
            del scheduler_request["schedules"]
            payload = str.encode(json.dumps(scheduler_request))

        # start the lambda function
        resp = self.lambda_client.invoke(
            FunctionName=self._env.scheduling_request_handler_name,
            InvocationType="Event",
            LogType="None",
            Payload=payload,
        )
        if resp["StatusCode"] != 202:
            self._logger.error(
                f"Error executing {self._context.function_name}, version {self._context.function_version} with configuration {payload.decode()}"
            )

        result = {
            "service": scheduler_request["service"],
            "account": scheduler_request["account"],
            "region": scheduler_request["region"],
            "lambda_invoke_result": resp["StatusCode"],
            "lambda_request_id": resp["ResponseMetadata"]["RequestId"],
        }
        return result


def prefetch_schedules_and_periods(
    env: OrchestratorEnvironment, logger: Logger
) -> tuple[InMemoryScheduleDefinitionStore, InMemoryPeriodDefinitionStore]:
    schedules, schedule_errors = prefetch_schedules(env)
    periods, period_errors = prefetch_periods(env)

    cached_schedule_store = InMemoryScheduleDefinitionStore(schedules)
    cached_period_store = InMemoryPeriodDefinitionStore(periods)

    exceptions: list[InvalidScheduleDefinition | InvalidPeriodDefinition] = list()
    exceptions.extend(schedule_errors)
    exceptions.extend(period_errors)

    for schedule in list(cached_schedule_store.find_all().values()):
        # filter and warn about schedules referencing periods that do not exist
        try:
            schedule.to_instance_schedule(cached_period_store)
        except InvalidScheduleDefinition as e:
            cached_schedule_store.delete(schedule.name)
            exceptions.append(
                InvalidScheduleDefinition(
                    f"Invalid Schedule Definition:\n{json.dumps(schedule.to_item(), indent=2)}\n{e}"
                )
            )

    logger.info(f"prefetched {len(schedules)} schedules and {len(periods)} periods")
    if exceptions:
        exception_list = "\n\n".join(map(str, exceptions))
        logger.error(
            f"There are incorrectly configured schedules/periods!\n{exception_list}"
        )

    return cached_schedule_store, cached_period_store


def prefetch_schedules(
    env: OrchestratorEnvironment,
) -> tuple[Mapping[str, ScheduleDefinition], list[InvalidScheduleDefinition]]:
    dynamo_store = DynamoScheduleDefinitionStore(env.config_table_name)
    schedules, exceptions = dynamo_store.find_all_with_errors()
    return schedules, exceptions


def prefetch_periods(
    env: OrchestratorEnvironment,
) -> tuple[Mapping[str, PeriodDefinition], list[InvalidPeriodDefinition]]:
    dynamo_store = DynamoPeriodDefinitionStore(env.config_table_name)
    periods, exceptions = dynamo_store.find_all_with_errors()
    return periods, exceptions
