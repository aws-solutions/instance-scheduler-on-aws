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
from datetime import datetime

from configuration.config_admin import ConfigAdmin
from util.logger import Logger

LOG_STREAM = "{}-{:0>4d}{:0>2d}{:0>2d}"


class AdminApiRequestHandler(object):
    """
    Class to handles requests from REST admin API
    """
    def __init__(self, event, context):
        """
        Initializes handle instance
        :param event: event to handle
        :param context: lambda context
        """
        self._event = event
        self._context = context
        self._logger = None

    @property
    def action(self):
        """
        Retrieves admin REST api action from the event
        :return: name of the action of the event
        """
        return self._event["action"]

    @staticmethod
    def is_handling_request(event):
        """
        Returns True if the handler can handle the event
        :param event: tested event
        :return: True if the handles does handle the tested event
        """
        return "action" in event and "resource-path" in event

    def handle_request(self):
        """
        Handles the event
        :return: result of handling the event, result send back to REST admin api
        """

        # Setup logging
        classname = self.__class__.__name__
        dt = datetime.utcnow()
        logstream = LOG_STREAM.format(classname, dt.year, dt.month, dt.day)
        self._logger = Logger(logstream=logstream, buffersize=20, context=self._context)

        with Logger(logstream=logstream, buffersize=20, context=self._context) as logger:

            logger.info("Handler {} : Received request {}", self.__class__.__name__, json.dumps(self._event))

            # get access to admin api
            admin = ConfigAdmin(logger=logger, context=self._context)

            # get api action and map it to a function in the admin API
            fn = getattr(admin, self.action)
            if fn is None:
                raise ValueError("Action {} does not exist".format(self.action))

            # build parameters for admin API call
            temp = self._event.get("params", {})
            params = {p: temp[p] for p in temp}
            if "name" in self._event:
                params["name"] = self._event["name"]
            logger.info("Calling \"{}\" with parameters {}", fn.__name__, params)
            # call the admin API
            result = fn(**params)
            logger.info("Call result is {}", result)
            return result
