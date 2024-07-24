# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import json
import traceback
from collections.abc import Mapping
from datetime import datetime, timezone
from time import time
from typing import TYPE_CHECKING, Any, Final, Sequence

from instance_scheduler import util
from instance_scheduler.handler.base import MainHandler
from instance_scheduler.handler.cfn_schedule import CfnScheduleHandler
from instance_scheduler.handler.cli.cli_request_handler import CliRequestHandler
from instance_scheduler.handler.config_resource import SchedulerSetupHandler
from instance_scheduler.handler.environments.main_lambda_environment import (
    MainLambdaEnv,
)
from instance_scheduler.util.logger import Logger

if TYPE_CHECKING:
    from aws_lambda_powertools.utilities.typing import LambdaContext
else:
    LambdaContext = object

LOG_STREAM = "InstanceScheduler-{:0>4d}{:0>2d}{:0>2d}"

handlers: Final[Sequence[type[MainHandler[Any]]]] = (
    SchedulerSetupHandler,
    CfnScheduleHandler,
    CliRequestHandler,
)


def lambda_handler(event: Mapping[str, Any], context: LambdaContext) -> Any:
    dt = datetime.now(timezone.utc)
    env = MainLambdaEnv.from_env()
    log_stream = LOG_STREAM.format(dt.year, dt.month, dt.day)
    result = {}
    with Logger(
        log_group=env.log_group,
        log_stream=log_stream,
        topic_arn=env.topic_arn,
        debug=env.enable_debug_logging,
    ) as logger:
        logger.info("InstanceScheduler, version {}".format(env.solution_version))

        logger.debug("Event is {}", util.safe_json(event, indent=3))

        for handler_type in handlers:
            if handler_type.is_handling_request(event):
                start = time()
                handler = handler_type(event, context, env)
                logger.info("Handler is {}".format(handler_type.__name__))
                try:
                    result = handler.handle_request()
                except Exception as e:
                    logger.error(
                        "Error handling request {} by handler {}: ({})\n{}",
                        json.dumps(event),
                        handler_type.__name__,
                        e,
                        traceback.format_exc(),
                    )
                execution_time = round(float((time() - start)), 3)
                logger.info("Handling took {} seconds", execution_time)
                return result
        logger.debug(
            "Request was not handled, no handler was able to handle this type of request {}",
            json.dumps(event),
        )
