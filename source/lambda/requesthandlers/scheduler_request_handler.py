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

import os
from datetime import datetime

import configuration
import schedulers
from configuration.scheduler_config_builder import SchedulerConfigBuilder
from schedulers import SCHEDULER_TYPES
from schedulers.instance_scheduler import InstanceScheduler
from util.logger import Logger

INF_HANDLER = "Handler {} scheduling request for service(s) {}, account(s) {}, region(s) {} at {}"
INF_SCHEDULER_RESULT = "Scheduler result {}"

LOG_STREAM = "{}-{:0>4d}{:0>2d}{:0>2d}"
LOG_STREAM_PREFIX = "Scheduler"


class SchedulerRequestHandler:
    """
    Class that handled the execution of the scheduler
    """

    def __init__(self, event, context):
        self._context = context
        self._event = event
        self._configuration = None
        self._logger = None

    @staticmethod
    def is_handling_request(event):
        """
        Tests if this handler handles the event
        :param event: tested event
        :return: True if the handler handles the event
        """
        action = event.get("action", "")
        return action == "scheduler:run"

    @property
    def lambda_account(self):
        """
        Returns the name of the lambda account
        :return: lambda account
        """
        if "account" in self._event:
            return self._event["account"]
        return os.getenv(configuration.ENV_ACCOUNT)

    @property
    def state_table(self):
        """
        Returns the name of the configuration table
        :return: name of the configuration table
        """
        return os.getenv(configuration.ENV_STATE)

    @property
    def configuration(self):
        """
        Gets the configuration passed in the event
        :return: scheduler configuration
        """
        if self._configuration is None:
            # need to reconstruct configuration from dictionary in event
            self._configuration = SchedulerConfigBuilder.configuration_from_dict(self._event["configuration"])
            # for large configurations the schedules are not passed in the event, need to reload these here
            if len(self._configuration.schedules) == 0:
                loaded_config = configuration.get_scheduler_configuration(self._logger)
                self._configuration.schedules = loaded_config.schedules
        return self._configuration

    @property
    def account_names(self):
        """
        Iterates account names from the configuration
        :return: account names to process
        """

        if self.configuration.schedule_lambda_account:
            yield self.lambda_account

        for role in self.configuration.cross_account_roles:
            account_name = schedulers.account_from_role(role)
            yield account_name

    def handle_request(self):
        """
        Handles the event
        :return:
        """
        result = {}

        account_names = list(self.account_names)
        for service in self.configuration.scheduled_services:
            # gets the implementation that handles the actual scheduling for the service
            service_strategy = SCHEDULER_TYPES[service]()
            # create a scheduler and pass the service strategy
            scheduler = InstanceScheduler(service=service_strategy, scheduler_configuration=self.configuration)

            # setup logging for the service/account/region
            s = "-".join([LOG_STREAM_PREFIX, service, "-".join(account_names), "-".join(self.configuration.regions)])
            dt = datetime.utcnow()
            logstream = LOG_STREAM.format(s, dt.year, dt.month, dt.day)
            self._logger = Logger(logstream=logstream, buffersize=60 if self.configuration.trace else 30, context=self._context,
                                  debug=self.configuration.trace)

            try:
                self._logger.info(INF_HANDLER.format(
                    self.__class__.__name__,
                    ", ".join(self.configuration.scheduled_services),
                    ", ".join(list(self.account_names)),
                    ", ".join(list(self.configuration.regions)),
                    datetime.now()))

                # run the scheduler for the service
                result[service] = scheduler.run(state_table=self.state_table, scheduler_config=self.configuration,
                                                lambda_account=self.lambda_account, context=self._context, logger=self._logger)
                self._logger.info(INF_SCHEDULER_RESULT, result[service])

            finally:
                self._logger.flush()

        return result
