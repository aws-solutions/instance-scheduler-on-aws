# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import json
import traceback
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Literal, Optional, TypedDict, TypeGuard, cast

from instance_scheduler.boto_retry import get_client_with_standard_retry
from instance_scheduler.handler.environments.orchestrator_environment import (
    OrchestratorEnvironment,
)
from instance_scheduler.handler.scheduling_request import SchedulingRequest
from instance_scheduler.model.ddb_config_item import DdbConfigItem
from instance_scheduler.model.period_definition import (
    InvalidPeriodDefinition,
    PeriodDefinition,
)
from instance_scheduler.model.schedule_definition import (
    InvalidScheduleDefinition,
    ScheduleDefinition,
)
from instance_scheduler.model.store.ddb_config_item_store import DdbConfigItemStore
from instance_scheduler.model.store.dynamo_period_definition_store import (
    DynamoPeriodDefinitionStore,
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
from instance_scheduler.model.store.period_definition_store import PeriodDefinitionStore
from instance_scheduler.model.store.schedule_definition_store import (
    ScheduleDefinitionStore,
)
from instance_scheduler.ops_metrics.metric_type.deployment_description_metric import (
    DeploymentDescriptionMetric,
    ScheduleFlagCounts,
)
from instance_scheduler.ops_metrics.metrics import collect_metric, should_collect_metric
from instance_scheduler.util import safe_json
from instance_scheduler.util.logger import Logger
from instance_scheduler.util.scheduling_target import get_account_ids, list_all_targets
from instance_scheduler.util.validation import ValidationException, validate_string

if TYPE_CHECKING:
    from aws_lambda_powertools.utilities.typing import LambdaContext
else:
    LambdaContext = object

LOG_STREAM = "{}-{:0>4d}{:0>2d}{:0>2d}"


class OrchestrationRequest(TypedDict):
    scheduled_action: Literal["run_orchestrator"]


def validate_orchestration_request(
    untyped_dict: Mapping[str, Any]
) -> TypeGuard[OrchestrationRequest]:
    validate_string(untyped_dict, "scheduled_action", required=True)

    if untyped_dict["scheduled_action"] != "run_orchestrator":
        raise ValidationException(
            f"unknown scheduled_action. received '{untyped_dict['scheduled_action']}', expected 'run_orchestrator'"
        )

    return True


LAMBDA_PAYLOAD_CAPACITY_BYTES = (
    200_000  # is actually 256_000 but this provides some overhead
)


def handle_orchestration_request(
    event: Mapping[str, Any], context: LambdaContext
) -> Any:
    env = OrchestratorEnvironment.from_env()
    dt = datetime.now(timezone.utc)
    logstream = "SchedulingOrchestratorHandler-{:0>4d}{:0>2d}{:0>2d}".format(
        dt.year, dt.month, dt.day
    )
    logger = Logger(
        log_group=env.log_group,
        log_stream=logstream,
        topic_arn=env.topic_arn,
        debug=env.enable_debug_logging,
    )

    with logger:
        try:
            validate_orchestration_request(event)
            event = cast(OrchestrationRequest, event)
            handler = SchedulingOrchestratorHandler(event, context, env, logger)
            return handler.handle_request()
        except Exception as e:
            # log error to SNS, then let the lambda execution fail
            logger.error(
                "Error handling orchestration registration request {}: ({})\n{}",
                safe_json(event),
                e,
                traceback.format_exc(),
            )
            raise e


class SchedulingOrchestratorHandler:
    """
    Handles event from cloudwatch rule timer
    """

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

    @property
    def lambda_client(self) -> Any:
        """
        Get the lambda client
        :return: lambda client
        """
        if self._lambda_client is None:
            self._lambda_client = get_client_with_standard_retry("lambda")
        return self._lambda_client

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

            ddb_config_item_store = DdbConfigItemStore(self._env.config_table_name)

            schedules, periods = prefetch_schedules_and_periods(self._env, self._logger)
            ddb_config_item = ddb_config_item_store.get()

            serialized_schedules = schedules.serialize()
            serialized_periods = periods.serialize()

            result = []

            scheduler_request = None
            for target in list_all_targets(
                ddb_config_item, self._env, self._logger, self._context
            ):
                current_dt_str = datetime.now(timezone.utc).isoformat()
                scheduler_request = SchedulingRequest(
                    action="scheduler:run",
                    account=target.account,
                    region=target.region,
                    service=target.service,
                    current_dt=current_dt_str,
                    dispatch_time=datetime.now(timezone.utc).isoformat(),
                )
                scheduler_request["schedules"] = serialized_schedules
                scheduler_request["periods"] = serialized_periods
                result.append(self._run_scheduling_lambda(scheduler_request))

            if not result:
                self._logger.warning(
                    "No targets to schedule. Please ensure you have correctly configured your target"
                    " accounts and regions in your CloudFormation parameters"
                )

            if should_collect_metric(DeploymentDescriptionMetric):
                collect_metric(
                    self.build_deployment_description_metric(
                        ddb_config_item,
                        schedules,
                        periods,
                        self._env,
                        self._context,
                        sample_scheduling_request=scheduler_request,
                    ),
                    logger=self._logger,
                )

            return result
        finally:
            self._logger.flush()

    def _run_scheduling_lambda(
        self, scheduler_request: SchedulingRequest
    ) -> dict[str, Any]:
        # runs a service/account/region subset of the configuration as a new lambda function
        self._logger.info(
            "Starting lambda function for scheduling {} instances for account {} in region {}",
            scheduler_request["service"],
            scheduler_request["account"],
            scheduler_request["region"],
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
                "Error executing {}, version {} with configuration {}",
                self._context.function_name,
                self._context.function_version,
                payload,
            )

        result = {
            "service": scheduler_request["service"],
            "account": scheduler_request["account"],
            "region": scheduler_request["region"],
            "lambda_invoke_result": resp["StatusCode"],
            "lambda_request_id": resp["ResponseMetadata"]["RequestId"],
        }
        return result

    def build_deployment_description_metric(
        self,
        ddb_config_item: DdbConfigItem,
        schedule_store: ScheduleDefinitionStore,
        period_store: PeriodDefinitionStore,
        env: OrchestratorEnvironment,
        lambda_context: LambdaContext,
        sample_scheduling_request: Optional[SchedulingRequest],
    ) -> DeploymentDescriptionMetric:
        flag_counts = ScheduleFlagCounts()
        schedules = schedule_store.find_all()
        periods = period_store.find_all()
        for schedule in schedules.values():
            flag_counts.stop_new_instances += schedule.stop_new_instances in [
                True,
                None,
            ]  # default is also true
            flag_counts.enforced += schedule.enforced is True
            flag_counts.retain_running += schedule.retain_running is True
            flag_counts.hibernate += schedule.hibernate is True
            flag_counts.override += schedule.override_status is not None
            flag_counts.use_ssm_maintenance_window += bool(
                schedule.ssm_maintenance_window
            )
            flag_counts.non_default_timezone += schedule.timezone != str(
                env.default_timezone
            )

        metric = DeploymentDescriptionMetric(
            services=get_enabled_services(env),
            regions=env.schedule_regions,
            num_accounts=sum(
                1
                for _ in get_account_ids(
                    ddb_config_item, self._env, self._logger, self._context
                )
            ),
            num_schedules=len(schedules),
            num_cfn_schedules=_count_cfn_schedules(schedules),
            num_one_sided_schedules=_count_one_sided_schedules(schedules, periods),
            schedule_flag_counts=flag_counts,
            default_timezone=str(env.default_timezone),
            create_rds_snapshots=env.enable_rds_snapshots,
            schedule_interval_minutes=env.scheduler_frequency_minutes,
            memory_size_mb=lambda_context.memory_limit_in_mb,
            using_organizations=env.enable_aws_organizations,
            enable_ec2_ssm_maintenance_windows=env.enable_ec2_ssm_maintenance_windows,
            ops_dashboard_enabled=env.ops_dashboard_enabled,
            num_started_tags=len(env.start_tags),
            num_stopped_tags=len(env.stop_tags),
            approximate_lambda_payload_size_bytes=(
                len(str.encode(json.dumps(sample_scheduling_request)))
                if sample_scheduling_request
                else 0
            ),
        )

        return metric


def strip_schedules_and_periods(event_dict: dict[str, Any]) -> None:
    event_dict["schedules"] = {}
    event_dict["periods"] = {}


def _count_cfn_schedules(schedules: Mapping[str, ScheduleDefinition]) -> int:
    count = 0
    for schedule in schedules.values():
        count += bool(schedule.configured_in_stack)
    return count


def _count_one_sided_schedules(
    schedules: Mapping[str, ScheduleDefinition], periods: Mapping[str, PeriodDefinition]
) -> int:
    def is_one_sided_period(period: PeriodDefinition | None) -> bool:
        if period is None:
            return False
        return bool(
            (period.begintime and not period.endtime)
            or (not period.begintime and period.endtime)
        )  # logical xor

    count = 0
    for schedule in schedules.values():
        for schedule_period in schedule.periods:
            if is_one_sided_period(periods[schedule_period.name]):
                count += 1
                break
    return count


def get_enabled_services(env: OrchestratorEnvironment) -> list[str]:
    enabled_services = []
    if env.enable_ec2_service:
        enabled_services.append("ec2")
    if env.enable_rds_service:
        enabled_services.append("rds")
    if env.enable_rds_clusters:
        enabled_services.append("rds-clusters")
    if env.enable_neptune_service:
        enabled_services.append("neptune")
    if env.enable_docdb_service:
        enabled_services.append("docdb")
    if env.enable_asg_service:
        enabled_services.append("asg")
    return enabled_services


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

    logger.info("prefetched {} schedules and {} periods", len(schedules), len(periods))
    if exceptions:
        logger.error(
            "There are incorrectly configured schedules/periods!\n{}",
            "\n\n".join(map(str, exceptions)),
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
