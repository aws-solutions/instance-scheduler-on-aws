# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0


import json
import os
import traceback
from datetime import datetime
from time import time

from instance_scheduler import configuration
from instance_scheduler import util
from instance_scheduler.requesthandlers.admin_cli_request_handler import (
    AdminCliRequestHandler,
)
from instance_scheduler.requesthandlers.cloudwatch_event_handler import (
    CloudWatchEventHandler,
)
from instance_scheduler.requesthandlers.schedule_resource_handler import (
    ScheduleResourceHandler,
)
from instance_scheduler.requesthandlers.scheduler_request_handler import (
    SchedulerRequestHandler,
)
from instance_scheduler.requesthandlers.scheduler_setup_handler import (
    SchedulerSetupHandler,
)
from instance_scheduler.requesthandlers.eventbus_request_handler import (
    EventBusRequestHandler,
)
from instance_scheduler.util.logger import Logger
from instance_scheduler.version import VERSION

LOG_STREAM = "InstanceScheduler-{:0>4d}{:0>2d}{:0>2d}"


def lambda_handler(event, context):
    try:
        dt = datetime.utcnow()
        log_stream = LOG_STREAM.format(dt.year, dt.month, dt.day)
        result = {}
        with Logger(
            logstream=log_stream,
            buffersize=20,
            context=context,
            debug=util.as_bool(os.getenv(configuration.ENV_TRACE, False)),
        ) as logger:
            logger.info("InstanceScheduler, version {}".format(VERSION))

            logger.debug("Event is {}", util.safe_json(event, indent=3))

            for handler_type in [
                SchedulerRequestHandler,
                SchedulerSetupHandler,
                ScheduleResourceHandler,
                AdminCliRequestHandler,
                CloudWatchEventHandler,
                EventBusRequestHandler,
            ]:
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
        configuration.unload_scheduler_configuration()
