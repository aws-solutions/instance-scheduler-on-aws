# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from collections.abc import Iterable, Iterator
from typing import TYPE_CHECKING, Any, Final
from uuid import uuid4

from aws_lambda_powertools.logging import Logger
from aws_lambda_powertools.utilities.data_classes import DynamoDBStreamEvent
from aws_lambda_powertools.utilities.data_classes.dynamo_db_stream_event import (
    DynamoDBRecord,
    DynamoDBRecordEventName,
)

from instance_scheduler.handler.asg_orchestrator import orchestrate_asgs
from instance_scheduler.handler.environments.asg_orch_env import AsgOrchEnv
from instance_scheduler.model.store.dynamo_schedule_definition_store import (
    DynamoScheduleDefinitionStore,
)
from instance_scheduler.model.store.schedule_definition_store import (
    ScheduleDefinitionStore,
)
from instance_scheduler.util.sns_handler import SnsHandler

if TYPE_CHECKING:
    from aws_lambda_powertools.utilities.typing import LambdaContext
else:
    LambdaContext = object

logger: Final = Logger(log_uncaught_exceptions=True, use_rfc3339=True)


@logger.inject_lambda_context(log_event=True)
def lambda_handler(event: dict[str, Any], context: LambdaContext) -> None:
    env: Final = AsgOrchEnv.from_env()
    sns_handler: Final = SnsHandler(
        topic_arn=env.issues_topic_arn,
        log_group_name=context.log_group_name,
        log_stream_name=context.log_stream_name,
        raise_exceptions=env.logger_raise_exceptions,
    )
    logger.addHandler(sns_handler)
    correlation_id: Final = uuid4()
    logger.set_correlation_id(str(correlation_id))

    stream_event: Final = DynamoDBStreamEvent(event)
    store: Final = DynamoScheduleDefinitionStore(env.config_table_name)
    schedule_names: Final = list(
        set(schedule_names_from_records(stream_event.records, store))
    )

    orchestrate_asgs(env, context, schedule_names)


def schedule_names_from_records(  # NOSONAR
    records: Iterable[DynamoDBRecord], store: ScheduleDefinitionStore
) -> Iterator[str]:
    for record in records:
        if record.event_name not in {
            DynamoDBRecordEventName.INSERT,
            DynamoDBRecordEventName.MODIFY,
        }:
            # these should be filtered already, but just in case
            continue

        ddb = record.dynamodb
        if ddb is None:
            continue

        keys = ddb.keys
        if keys is None:
            continue

        record_type: str | None = keys.get("type")
        if record_type is None:
            continue

        record_name: str | None = keys.get("name")
        if record_name is None:
            continue

        if record_type == "schedule":
            yield record_name
        elif record_type == "period":
            try:
                # this is not very efficient
                # we should make one pass, finding all schedules given a list of period names
                yield from store.find_by_period(record_name).keys()
            except Exception:
                logger.exception(
                    f"Unable to determine schedules to update based on period {record_name}"
                )
