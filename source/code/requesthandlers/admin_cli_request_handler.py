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

import jmespath

import configuration
from configuration.config_admin import ConfigAdmin
from util import safe_json
from util.logger import Logger

CLI_SOURCE = "scheduler.cli"

LOG_STREAM = "{}-{:0>4d}{:0>2d}{:0>2d}"


class AdminCliRequestHandler(object):
    """
    Class to handles requests from admin CLI
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

        self.additional_parameters = {
            "delete-period": {"exception_if_not_exists": True},
            "delete-schedule": {"exception_if_not_exists": True}
        }

        self.transform_parameters = {
            "metrics": "use-metrics"
        }

        self.commands = {
            "create-period": "create_period",
            "create-schedule": "create_schedule",
            "delete-period": "delete_period",
            "delete-schedule": "delete_schedule",
            "describe-periods": "list_periods" if self.parameters.get(configuration.NAME) is None else "get_period",
            "describe-schedule-usage": "get_schedule_usage",
            "describe-schedules": "list_schedules" if self.parameters.get(configuration.NAME) is None else "get_schedule",
            "update-period": "update_period",
            "update-schedule": "update_schedule"
        }

        self.transformations = {
            "get_period": "{Periods:[Period]}",
            "get_schedule": "{Schedules:[Schedule]}"
        }

        # Setup logging
        classname = self.__class__.__name__
        dt = datetime.utcnow()
        log_stream = LOG_STREAM.format(classname, dt.year, dt.month, dt.day)
        self._logger = Logger(logstream=log_stream, buffersize=20, context=self._context)

    @property
    def action(self):
        """
        Retrieves admin REST api action from the event
        :return: name of the action of the event
        """
        return self._event["action"]

    @property
    def parameters(self):
        params = self._event.get("parameters", {})
        for p in params:
            if p in self.transform_parameters:
                params[self.transform_parameters[p]] = params[p]
                del params[p]
        extra = self.additional_parameters.get(self.action, {})
        params.update(extra)
        return {p.replace("-", "_"): params[p] for p in params}

    @staticmethod
    def is_handling_request(event):
        """
        Returns True if the handler can handle the event
        :param event: tested event
        :return: True if the handles does handle the tested event
        """

        if event.get("source", "") != CLI_SOURCE:
            return False
        return "action" in event

    # noinspection SpellCheckingInspection
    def handle_request(self):
        """
        Handles the event
        :return: result of handling the event, result send back to REST admin api
        """

        def snake_to_pascal_case(s):
            converted = ""
            s = s.strip("_").capitalize()
            i = 0

            while i < len(s):
                if s[i] == "_":
                    i += 1
                    converted += s[i].upper()
                else:
                    converted += s[i]
                i += 1

            return converted

        # noinspection PyShadowingNames
        def dict_to_pascal_case(d):

            d_result = {}

            if isinstance(d, dict):
                for i in d:
                    key = snake_to_pascal_case(i)
                    d_result[key] = dict_to_pascal_case(d[i])
                return d_result

            elif isinstance(d, list):
                return [dict_to_pascal_case(l) for l in d]

            return d

        try:
            self._logger.info("Handler {} : Received CLI request {}", self.__class__.__name__, json.dumps(self._event))

            # get access to admin api
            admin = ConfigAdmin(logger=self._logger, context=self._context)

            # get api action and map it to a function in the admin API
            fn_name = self.commands.get(self.action, None)
            if fn_name is None:
                raise ValueError("Command {} does not exist".format(self.action))
            fn = getattr(admin, fn_name)

            # calling the mapped admin api method
            self._logger.info("Calling \"{}\" with parameters {}", fn.__name__, self.parameters)
            api_result = fn(**self.parameters)

            # convert to awscli PascalCase output format
            result = dict_to_pascal_case(api_result)

            # perform output transformation
            if fn_name in self.transformations:
                result = jmespath.search(self.transformations[fn_name], result)

            # log formatted result
            json_result = safe_json(result, 3)
            self._logger.info("Call result is {}", json_result)

            return result

        except Exception as ex:
            self._logger.info("Call failed, error is {}", str(ex))
            return {"Error": str(ex)}
        finally:
            self._logger.flush()
