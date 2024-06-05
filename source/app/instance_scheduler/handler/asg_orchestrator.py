# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import json
from datetime import datetime, timezone
from itertools import product
from typing import TYPE_CHECKING, Any, Final
from uuid import uuid4

from aws_lambda_powertools.logging import Logger
from boto3.session import Session

from instance_scheduler.boto_retry import get_client_with_standard_retry
from instance_scheduler.handler.environments.asg_orch_env import AsgOrchEnv
from instance_scheduler.handler.scheduling_request import SchedulingRequest
from instance_scheduler.model.store.ddb_config_item_store import DdbConfigItemStore
from instance_scheduler.util.scheduling_target import get_account_ids
from instance_scheduler.util.sns_handler import SnsHandler

if TYPE_CHECKING:
    from aws_lambda_powertools.utilities.typing import LambdaContext
    from mypy_boto3_lambda.client import LambdaClient
else:
    LambdaContext = object
    LambdaClient = object

logger: Final = Logger(log_uncaught_exceptions=True, use_rfc3339=True)


@logger.inject_lambda_context(log_event=True)
def lambda_handler(_: dict[str, Any], context: LambdaContext) -> None:
    env: Final = AsgOrchEnv.from_env()
    sns_handler: Final = SnsHandler(
        topic_arn=env.issues_topic_arn,
        log_group_name=context.log_group_name,
        log_stream_name=context.log_stream_name,
        raise_exceptions=env.logger_raise_exceptions,
    )
    logger.addHandler(sns_handler)
    # correlation ID should eventually come from source event
    logger.set_correlation_id(str(uuid4()))

    orchestrate_asgs(env, context)


def orchestrate_asgs(
    env: AsgOrchEnv, context: LambdaContext, schedule_names: list[str] | None = None
) -> None:
    ddb_config_item_store: Final = DdbConfigItemStore(env.config_table_name)
    ddb_config_item: Final = ddb_config_item_store.get()
    account_ids: Final = get_account_ids(ddb_config_item, env, logger, context)
    regions: Final = (
        env.schedule_regions if env.schedule_regions else [Session().region_name]
    )
    lambda_client: LambdaClient = get_client_with_standard_retry("lambda")
    dispatch_time: Final = datetime.now(timezone.utc).isoformat()

    for account_id, region in product(account_ids, regions):
        try:
            request = SchedulingRequest(
                action="scheduler:run",
                account=account_id,
                region=region,
                service="asg",
                current_dt=dispatch_time,
                dispatch_time=dispatch_time,
            )
            if schedule_names is not None:
                request["schedule_names"] = schedule_names
            lambda_client.invoke(
                FunctionName=env.asg_scheduler_name,
                InvocationType="Event",
                Payload=str.encode(json.dumps(request)),
            )
        except Exception as err:
            logger.error(
                {
                    "Message": "Failed to invoke ASG scheduling request handler",
                    "Error": err,
                    "Request": request,
                }
            )
