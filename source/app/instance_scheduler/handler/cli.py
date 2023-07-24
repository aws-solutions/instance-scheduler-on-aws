# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import json
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, TypeGuard

import jmespath

from instance_scheduler import configuration
from instance_scheduler.configuration.config_admin import ConfigAdmin
from instance_scheduler.handler.base import Handler
from instance_scheduler.ops_metrics.metric_type.cli_request_metric import (
    CliRequestMetric,
)
from instance_scheduler.ops_metrics.metrics import collect_metric
from instance_scheduler.util import safe_json
from instance_scheduler.util.app_env import get_app_env
from instance_scheduler.util.logger import Logger

if TYPE_CHECKING:
    from aws_lambda_powertools.utilities.typing import LambdaContext
else:
    LambdaContext = object

CLI_SOURCE = "scheduler.cli"

LOG_STREAM = "{}-{:0>4d}{:0>2d}{:0>2d}"

AdminCliRequest = dict[str, Any]


class CliHandler(Handler[AdminCliRequest]):
    """
    Class to handles requests from admin CLI
    """

    def __init__(self, event: AdminCliRequest, context: LambdaContext) -> None:
        """
        Initializes handle instance
        :param event: event to handle
        :param context: lambda context
        """
        self._event = event
        self._context = context

        self.additional_parameters = {
            "delete-period": {"exception_if_not_exists": True},
            "delete-schedule": {"exception_if_not_exists": True},
        }

        self.transform_parameters = {"metrics": "use-metrics"}

        self.commands = {
            "create-period": "create_period",
            "create-schedule": "create_schedule",
            "delete-period": "delete_period",
            "delete-schedule": "delete_schedule",
            "describe-periods": "list_periods"
            if self.parameters.get(configuration.NAME) is None
            else "get_period",
            "describe-schedule-usage": "get_schedule_usage",
            "describe-schedules": "list_schedules"
            if self.parameters.get(configuration.NAME) is None
            else "get_schedule",
            "update-period": "update_period",
            "update-schedule": "update_schedule",
        }

        self.transformations = {
            "get_period": "{Periods:[Period]}",
            "get_schedule": "{Schedules:[Schedule]}",
        }

        # Setup logging
        classname = self.__class__.__name__
        app_env = get_app_env()
        dt = datetime.now(timezone.utc)
        log_stream = LOG_STREAM.format(classname, dt.year, dt.month, dt.day)
        self._logger = Logger(
            log_group=app_env.log_group,
            log_stream=log_stream,
            topic_arn=app_env.topic_arn,
            debug=app_env.enable_debug_logging,
        )

    @property
    def action(self) -> Any:
        """
        Retrieves admin REST api action from the event
        :return: name of the action of the event
        """
        return self._event["action"]

    @property
    def parameters(self) -> dict[Any, Any]:
        params = self._event.get("parameters", {})
        for p in params:
            if p in self.transform_parameters:
                params[self.transform_parameters[p]] = params[p]
                del params[p]
        extra = self.additional_parameters.get(self.action, {})
        params.update(extra)
        return {p.replace("-", "_"): params[p] for p in params}

    @staticmethod
    def is_handling_request(event: Mapping[str, Any]) -> TypeGuard[AdminCliRequest]:
        """
        Returns True if the handler can handle the event
        :param event: tested event
        :return: True if the handles does handle the tested event
        """

        if event.get("source", "") != CLI_SOURCE:
            return False
        return "action" in event

    def handle_request(self) -> Any:
        """
        Handles the event
        :return: result of handling the event, result send back to REST admin api
        """

        def snake_to_pascal_case(s: Any) -> Any:
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

        def dict_to_pascal_case(d: Any) -> Any:
            d_result = {}

            if isinstance(d, dict):
                for i in d:
                    key = snake_to_pascal_case(i)
                    d_result[key] = dict_to_pascal_case(d[i])
                return d_result

            elif isinstance(d, list):
                return [dict_to_pascal_case(item) for item in d]

            return d

        try:
            self._logger.info(
                "Handler {} : Received CLI request {}",
                self.__class__.__name__,
                json.dumps(self._event),
            )

            collect_metric(
                CliRequestMetric(command_used=self.action), logger=self._logger
            )

            # get access to admin api
            admin = ConfigAdmin(logger=self._logger, context=self._context)

            # get api action and map it to a function in the admin API
            fn_name = self.commands.get(self.action, None)
            if fn_name is None:
                raise ValueError("Command {} does not exist".format(self.action))
            fn = getattr(admin, fn_name)

            # calling the mapped admin api method
            self._logger.info(
                'Calling "{}" with parameters {}', fn.__name__, self.parameters
            )

            if fn.__name__ in [
                "create_period",
                "update_period",
                "create_schedule",
                "update_schedule",
            ]:
                api_result = fn(self.parameters)
            else:
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
