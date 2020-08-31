######################################################################################################################
#  Copyright 2019 Amazon.com, Inc. or its affiliates. All Rights Reserved.                                           #
#                                                                                                                    #
#  Licensed under the Apache License Version 2.0 (the "License"). You may not use this file except in compliance     #
#  with the License. A copy of the License is located at                                                             #
#                                                                                                                    #
#      http://www.apache.org/licenses/                                                                               #
#                                                                                                                    #
#  or in the "license" file accompanying this file. This file is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES #
#  OR CONDITIONS OF ANY KIND, express or implied. See the License for the specific language governing permissions    #
#  and limitations under the License.                                                                                #
######################################################################################################################

import json
import os
import traceback
from datetime import datetime
from time import time

import configuration
import util
from requesthandlers.admin_cli_request_handler import AdminCliRequestHandler
from requesthandlers.cloudwatch_event_handler import CloudWatchEventHandler
from requesthandlers.schedule_resource_handler import ScheduleResourceHandler
from requesthandlers.scheduler_request_handler import SchedulerRequestHandler
from requesthandlers.scheduler_setup_handler import SchedulerSetupHandler
from util.logger import Logger
from version import VERSION

LOG_STREAM = "InstanceScheduler-{:0>4d}{:0>2d}{:0>2d}"


# load models for services that have not have their latest models deployed to Lambda
def load_models():
    cdw = os.getcwd()
    models = os.path.join(cdw, "models")
    aws_data_path = os.getenv("AWS_DATA_PATH", None)
    if aws_data_path is not None:
        aws_data_path = ":".join([aws_data_path, models])
    else:
        aws_data_path = models
    os.environ["AWS_DATA_PATH"] = aws_data_path


load_models()


def lambda_handler(event, context):
    try:
        dt = datetime.utcnow()
        log_stream = LOG_STREAM.format(dt.year, dt.month, dt.day)
        result = {}
        with Logger(logstream=log_stream, buffersize=20, context=context,
                    debug=util.as_bool(os.getenv(configuration.ENV_TRACE, False))) as logger:

            logger.info("InstanceScheduler, version {}".format(VERSION))

            logger.debug("Event is {}", util.safe_json(event, indent=3))

            for handler_type in [SchedulerRequestHandler,
                                 SchedulerSetupHandler,
                                 ScheduleResourceHandler,
                                 AdminCliRequestHandler,
                                 CloudWatchEventHandler]:

                if handler_type.is_handling_request(event):
                    start = time()
                    handler = handler_type(event, context)
                    logger.info("Handler is {}".format(handler_type.__name__))
                    try:
                        result = handler.handle_request()
                    except Exception as e:
                        logger.error("Error handling request {} by handler {}: ({})\n{}", json.dumps(event), handler_type.__name__,
                                     e, traceback.format_exc())
                    execution_time = round(float((time() - start)), 3)
                    logger.info("Handling took {} seconds", execution_time)
                    return result
            logger.debug("Request was not handled, no handler was able to handle this type of request {}", json.dumps(event))
    finally:
        configuration.unload_scheduler_configuration()
