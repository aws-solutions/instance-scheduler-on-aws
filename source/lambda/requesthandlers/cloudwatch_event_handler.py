######################################################################################################################
#  Copyright 2021 Amazon.com, Inc. or its affiliates. All Rights Reserved.                                           #
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
from datetime import datetime

from util.logger import Logger
from requesthandlers.scheduler_ssm_handler import SchedulerSSMHandler

INF_HANDLER = "Handler {} : Received request {} at {}"
LOG_STREAM = "{}-{:0>4d}{:0>2d}{:0>2d}"
LOG_STREAM_PREFIX = "Scheduler"

class CloudWatchEventHandler:
    """
    Handles event from cloudwatch rule time
    """

    def __init__(self, event, context):

        self._context = context
        self._event = event
        self._configuration = None
        self._lambda_client = None

        # Setup logging
        classname = self.__class__.__name__
        dt = datetime.utcnow()
        logstream = LOG_STREAM.format(classname, dt.year, dt.month, dt.day)
        self._logger = Logger(logstream=logstream, buffersize=30, context=context)

    @staticmethod
    def is_handling_request(event):
        """
        Handler for cloudwatch event to run the scheduler
        :return: True
        """
        return event.get("detail-type", "") == "Scheduled Event"

    def handle_request(self):
        """
        Handles the CloudWatch Rule timer events
        :return:
        """
        try:
            self._logger.info(INF_HANDLER, self.__class__.__name__, json.dumps(self._event), datetime.now())
            handler = SchedulerSSMHandler(self._event, self._context)
            return handler.handle_request()
        finally:
            self._logger.flush()