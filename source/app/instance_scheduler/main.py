# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import json
import traceback
from datetime import datetime, timezone
from time import time
from typing import TYPE_CHECKING, Any, Mapping

from instance_scheduler import configuration, util
from instance_scheduler.handler import handlers
from instance_scheduler.util.app_env import get_app_env
from instance_scheduler.util.logger import Logger

if TYPE_CHECKING:
    from aws_lambda_powertools.utilities.typing import LambdaContext
else:
    LambdaContext = object

LOG_STREAM = "InstanceScheduler-{:0>4d}{:0>2d}{:0>2d}"


def lambda_handler(event: Mapping[str, Any], context: LambdaContext) -> Any:
    try:
        dt = datetime.now(timezone.utc)
        app_env = get_app_env()
        log_stream = LOG_STREAM.format(dt.year, dt.month, dt.day)
        result = {}
        with Logger(
            log_group=app_env.log_group,
            log_stream=log_stream,
            topic_arn=app_env.topic_arn,
            debug=app_env.enable_debug_logging,
        ) as logger:
            logger.info(
                "InstanceScheduler, version {}".format(app_env.solution_version)
            )

            logger.debug("Event is {}", util.safe_json(event, indent=3))

            for handler_type in handlers:
                if handler_type.is_handling_request(event):
                    start = time()
                    handler = handler_type(event, context)
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
    finally:
        configuration.unload_global_configuration()
