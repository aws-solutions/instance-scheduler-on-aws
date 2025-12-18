# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import inspect
import traceback
from collections.abc import Mapping
from datetime import datetime
from typing import (
    TYPE_CHECKING,
    Any,
    Final,
    Literal,
    NotRequired,
    TypedDict,
    TypeGuard,
    cast,
)

from instance_scheduler.configuration.scheduling_context import (
    SchedulingContext,
)
from instance_scheduler.handler.environments.scheduling_request_environment import (
    SchedulingRequestEnvironment,
)
from instance_scheduler.model.store.dynamo_period_definition_store import (
    DynamoPeriodDefinitionStore,
)
from instance_scheduler.model.store.dynamo_schedule_definition_store import (
    DynamoScheduleDefinitionStore,
)
from instance_scheduler.model.store.in_memory_period_definition_store import (
    InMemoryPeriodDefinitionStore,
    SerializedInMemoryPeriodDefinitionStore,
)
from instance_scheduler.model.store.in_memory_schedule_definition_store import (
    InMemoryScheduleDefinitionStore,
    SerializedInMemoryScheduleDefinitionStore,
)
from instance_scheduler.observability.cw_ops_insights import (
    CloudWatchOperationalInsights,
)
from instance_scheduler.observability.events import (
    report_scheduling_results_to_eventbus,
)
from instance_scheduler.observability.informational_tagging import (
    apply_informational_tags_for_results,
)
from instance_scheduler.observability.instance_counts import ServiceInstanceCounts
from instance_scheduler.observability.powertools_logging import (
    powertools_logger,
    should_log_events,
)
from instance_scheduler.ops_metrics.metrics import collect_metric
from instance_scheduler.scheduling.asg.asg_service import AsgService
from instance_scheduler.scheduling.ec2 import Ec2Service
from instance_scheduler.scheduling.rds import RdsService
from instance_scheduler.scheduling.scheduling_decision import ManagedInstance
from instance_scheduler.scheduling.scheduling_summary import SchedulingSummary
from instance_scheduler.util import safe_json
from instance_scheduler.util.session_manager import assume_role
from instance_scheduler.util.validation import (
    ValidationException,
    validate_string,
    validate_string_list,
)

if TYPE_CHECKING:
    from aws_lambda_powertools.utilities.typing import LambdaContext
else:
    LambdaContext = object
    LambdaClient = object


class SchedulingRequest(TypedDict):
    action: Literal["scheduler:run"]
    dispatch_time: str
    account: str
    service: str
    region: str
    current_dt: str
    schedules: NotRequired[SerializedInMemoryScheduleDefinitionStore]
    periods: NotRequired[SerializedInMemoryPeriodDefinitionStore]
    schedule_names: NotRequired[list[str]]


# powertools logger
logger: Final = powertools_logger()


def validate_scheduler_request(
    untyped_dict: Mapping[str, Any],
) -> TypeGuard[SchedulingRequest]:
    valid_keys = inspect.get_annotations(SchedulingRequest).keys()
    for key in untyped_dict.keys():
        if key not in valid_keys:
            raise ValidationException(
                f"{key} is not a valid parameter, valid parameters are {valid_keys}"
            )

    validate_string(untyped_dict, "dispatch_time", required=True)
    validate_string(untyped_dict, "account", required=True)
    validate_string(untyped_dict, "service", required=True)
    validate_string(untyped_dict, "region", required=True)
    validate_string(
        untyped_dict, "current_dt", required=True
    )  # todo: validate as ISO string

    if "schedules" in untyped_dict:
        InMemoryScheduleDefinitionStore.validate_serial_data(untyped_dict["schedules"])

    if "periods" in untyped_dict:
        InMemoryPeriodDefinitionStore.validate_serial_data(untyped_dict["periods"])

    if "schedule_names" in untyped_dict:
        validate_string_list(untyped_dict, "schedule_names", required=False)

    return True


@logger.inject_lambda_context(log_event=should_log_events(logger))
def handle_scheduling_request(event: Mapping[str, Any], _context: LambdaContext) -> Any:
    env = SchedulingRequestEnvironment.from_env()
    validate_scheduler_request(event)
    event = cast(SchedulingRequest, event)

    with logger.append_context_keys(
        service=event["service"],
        account=event["account"],
        region=event["region"],
    ):
        try:
            scheduling_context = build_scheduling_context(event, env)
            result_summary: SchedulingSummary[ManagedInstance]
            match event["service"]:
                case "ec2":
                    result_summary = SchedulingSummary(
                        Ec2Service(scheduling_context, env).schedule_target()  # type: ignore[arg-type]
                    )
                case "rds":
                    result_summary = SchedulingSummary(
                        RdsService(scheduling_context, env).schedule_target()  # type: ignore[arg-type]
                    )
                case "autoscaling":
                    result_summary = SchedulingSummary(
                        AsgService(scheduling_context).schedule_target()  # type: ignore[arg-type]
                    )
                case _:
                    raise ValueError(f"Unknown service: {event['service']}")

            apply_informational_tags_for_results(
                scheduling_context.assumed_role,
                result_summary.results,
                hub_stack_arn=env.hub_stack_name,
            )

            report_scheduling_results_to_eventbus(
                result_summary.results, scheduling_context.assumed_role, env
            )

            actions_taken_metric = result_summary.as_actions_taken_metric()
            if (
                actions_taken_metric.actions
            ):  # only report the metric when actions were actually taken
                collect_metric(actions_taken_metric, logger)

            if env.enable_ops_monitoring:
                CloudWatchOperationalInsights(env=env).send_metrics_to_cloudwatch(
                    ServiceInstanceCounts.for_scheduling_results(
                        result_summary.results
                    ),
                    scheduling_interval_minutes=env.scheduling_interval_minutes,
                )

            for result in result_summary.results:
                logger.info(
                    f"result for {result.instance.registry_info.arn} - {result.action_taken} ",
                    extra=result.to_json_log(),
                )
            return result_summary.to_json()

        except Exception as e:
            # log error to SNS, then let the lambda execution fail
            logger.error(
                f"Error handling scheduling request {safe_json(event)}: ({e})\n{traceback.format_exc()}"
            )
            raise e


def build_scheduling_context(
    event: SchedulingRequest, env: SchedulingRequestEnvironment
) -> SchedulingContext:
    current_dt = datetime.fromisoformat(event["current_dt"])
    role = assume_role(
        account=event["account"],
        region=event["region"],
        role_name=env.scheduler_role_name,
    )

    context = SchedulingContext(assumed_role=role, current_dt=current_dt, env=env)

    if "schedules" in event:
        context.schedule_store.preload_cache(
            InMemoryScheduleDefinitionStore.deserialize_to_sequence(
                event.get("schedules", [])
            )
        )
    else:
        dynamo_schedule_store = DynamoScheduleDefinitionStore(env.config_table_name)
        context.schedule_store.preload_cache(dynamo_schedule_store.find_all().values())

    if "periods" in event:
        context.period_store.preload_cache(
            InMemoryPeriodDefinitionStore.deserialize_to_sequence(
                event.get("periods", [])
            )
        )
    else:
        dynamo_period_store = DynamoPeriodDefinitionStore(env.config_table_name)
        context.period_store.preload_cache(dynamo_period_store.find_all().values())

    return context
