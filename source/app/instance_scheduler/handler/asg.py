# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Final, Set, cast
from uuid import uuid4

from aws_lambda_powertools.logging import Logger

from instance_scheduler.handler.environments.asg_env import AsgEnv
from instance_scheduler.handler.scheduling_request import (
    SchedulingRequest,
    validate_scheduler_request,
)
from instance_scheduler.model.period_definition import PeriodDefinition
from instance_scheduler.model.store.dynamo_period_definition_store import (
    DynamoPeriodDefinitionStore,
)
from instance_scheduler.model.store.dynamo_schedule_definition_store import (
    DynamoScheduleDefinitionStore,
)
from instance_scheduler.model.store.period_definition_store import (
    UnknownPeriodException,
)
from instance_scheduler.model.store.schedule_definition_store import (
    UnknownScheduleException,
)
from instance_scheduler.ops_metrics.metric_type.asg_count_metric import AsgCountMetric
from instance_scheduler.ops_metrics.metrics import collect_metric, get_metrics_env
from instance_scheduler.service.asg import AsgService
from instance_scheduler.util.session_manager import assume_role
from instance_scheduler.util.sns_handler import SnsHandler

if TYPE_CHECKING:
    from aws_lambda_powertools.utilities.typing import LambdaContext
else:
    LambdaContext = object

ASG_SERVICE: Final = "asg"


@dataclass(frozen=True)
class AsgMetricsDefinition:
    region: str
    num_tagged_auto_scaling_groups: int
    num_schedules: int


logger: Final = Logger(log_uncaught_exceptions=True, use_rfc3339=True)


@logger.inject_lambda_context(log_event=True)
def lambda_handler(event: dict[str, Any], context: LambdaContext) -> None:
    env: Final = AsgEnv.from_env()
    sns_handler: Final = SnsHandler(
        topic_arn=env.issues_topic_arn,
        log_group_name=context.log_group_name,
        log_stream_name=context.log_stream_name,
        raise_exceptions=env.logger_raise_exceptions,
    )
    logger.addHandler(sns_handler)
    # correlation ID should eventually come from event
    logger.set_correlation_id(str(uuid4()))

    validate_scheduler_request(event)
    request: Final = cast(SchedulingRequest, event)

    [num_tagged_auto_scaling_groups, num_schedules] = schedule_auto_scaling_groups(
        schedule_tag_key=env.schedule_tag_key,
        config_table_name=env.config_table_name,
        account_id=request["account"],
        region=request["region"],
        scheduling_role_name=env.asg_scheduling_role_name,
        asg_scheduled_tag_key=env.scheduled_tag_key,
        rule_prefix=env.rule_prefix,
        schedule_names=request.get("schedule_names"),
    )

    # Send operational metrics when the handler is called by ASG orchestrator.
    # ASG orchestrator does not send schedule names when calling the handler.
    if not request.get("schedule_names"):
        send_operational_metrics(
            AsgMetricsDefinition(
                region=request["region"],
                num_tagged_auto_scaling_groups=num_tagged_auto_scaling_groups,
                num_schedules=num_schedules,
            )
        )


def schedule_auto_scaling_groups(
    *,
    schedule_tag_key: str,
    config_table_name: str,
    account_id: str,
    region: str,
    scheduling_role_name: str,
    asg_scheduled_tag_key: str,
    rule_prefix: str,
    schedule_names: list[str] | None,
) -> tuple[int, int]:
    """
    Schedule auto scaling groups.
    When a schedule or periods are not found in the config DynamoDB table, it raises an exception.
    When there are schedule names provided, as schedules are updated,
    it always schedules auto scaling groups tagged with schedule names unless auto scaling groups are stopped.

    :param schedule_tag_key: a schedule tag key which is configured when launching the solution
    :param config_table_name: a config DynamoDB table name
    :param account_id: an AWS account ID
    :param region: an AWS region
    :param scheduling_role_name: a scheduling role name to assume
    :param asg_scheduled_tag_key: an auto scaling scheduled tag key: `scheduled`
    :param rule_prefix: an auto scaling group schedule rule prefix provided when launching the solution
    :param schedule_names: a list of schedule names which would be provided when updating schedules on the config DynamoDB table
    :return: number of tagged auto scaling groups and number of schedules in tags
    """

    period_store: Final = DynamoPeriodDefinitionStore(config_table_name)
    schedule_store: Final = DynamoScheduleDefinitionStore(config_table_name)
    is_schedule_override: Final[bool] = schedule_names is not None
    schedules_in_tag: Final[Set[str]] = set()
    num_tagged_auto_scaling_groups = 0

    session: Final = assume_role(
        account=account_id, region=region, role_name=scheduling_role_name
    )
    asg_service: Final = AsgService(
        assumed_asg_scheduling_role=session,
        schedule_tag_key=schedule_tag_key,
        asg_scheduled_tag_key=asg_scheduled_tag_key,
        rule_prefix=rule_prefix,
    )

    for group in asg_service.get_schedulable_groups(schedule_names):
        try:
            schedule_tag = list(
                filter(lambda tag: tag["Key"] == schedule_tag_key, group["Tags"])
            )

            if len(schedule_tag) == 0:
                continue

            num_tagged_auto_scaling_groups += 1

            schedule_name = schedule_tag[0]["Value"]
            schedule_definition = schedule_store.find_by_name(schedule_name)

            if not schedule_definition:
                raise UnknownScheduleException("No schedule found")

            schedules_in_tag.add(schedule_name)

            period_definitions: list[PeriodDefinition] = []

            for period_id in schedule_definition.periods:
                period_name = period_id.name
                period = period_store.find_by_name(period_name)

                if not period:
                    raise UnknownPeriodException("Period not found")

                period_definitions.append(period)

            asg_service.schedule_auto_scaling_group(
                group=group,
                schedule_definition=schedule_definition,
                period_definitions=period_definitions,
                is_schedule_override=is_schedule_override,
            )
        except Exception as err:
            logger.error(
                f'Error configuring schedule "{schedule_name}" for group "{group["AutoScalingGroupARN"]}": {err}',
            )

    return num_tagged_auto_scaling_groups, len(schedules_in_tag)


def send_operational_metrics(asg_metrics_definition: AsgMetricsDefinition) -> None:
    """
    Send operational metrics when the handler is called by ASG orchestrator.
    It only sends the number of tagged auto scaling groups and schedules associated with the auto scaling groups
    to align with other metrics. The metric is sent once a day so it does not increase the numbers for the day.

    :param asg_metrics_definition:
    """

    try:
        # `get_metrics_env` can raise `AppEnvError` so the exception should be captured.
        metrics_uuid = get_metrics_env().metrics_uuid
        current_time = datetime.now(timezone.utc)

        # To make sure to send once a day only
        if current_time.hour == metrics_uuid.int % 24:
            collect_metric(
                metric=AsgCountMetric(
                    service=ASG_SERVICE,
                    region=asg_metrics_definition.region,
                    num_instances=asg_metrics_definition.num_tagged_auto_scaling_groups,
                    num_schedules=asg_metrics_definition.num_schedules,
                ),
                logger=logger,
            )
    except Exception as e:
        logger.warning(f"Failed sending operational metrics: {e}")
