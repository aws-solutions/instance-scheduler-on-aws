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
from copy import copy
from datetime import datetime

import configuration
from boto_retry import get_client_with_retries
from configuration.scheduler_config_builder import SchedulerConfigBuilder
from schedulers import SCHEDULER_TYPES
from schedulers.instance_scheduler import InstanceScheduler
from util.logger import Logger

ERR_INVALID_ARN = "{} is not a valid ARN"
ERR_STARTING_LAMBDA = "Error executing {}, version {} with configuration {}"

INF_CONFIG_TABLE = "Configuration table is {}"
INF_HANDLER = "Handler {} : Received request {} at {}"
INF_RUN_SCHEDULER_LOCAL = "Running scheduling request for service(s) {}, account(s) {}, region(s) {}"
INF_SCHEDULER_RESULT = "Scheduler result is {}"
INF_STARTING_LAMBDA = "Starting lambda function for scheduling {} instances for account {} in region {}"

LOG_STREAM = "{}-{:0>4d}{:0>2d}{:0>2d}"
LOG_STREAM_PREFIX = "Scheduler"

WARN_DUPLICATE_ACCOUNT = "Account {} in arn {} is already processed, skipping role"


class CloudWatchEventHandler:
    """
    Handles event from cloudwatch rule time
    """
    TOP_LEVEL = 0
    SERVICE_LEVEL = 1
    ACCOUNT_LEVEL = 2
    REGION_LEVEL = 3

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

    @property
    def lambda_account(self):
        if "account" in self._event:
            return self._event["account"]
        return os.getenv(configuration.ENV_ACCOUNT)

    @property
    def lambda_client(self):
        """
        Get the lambda client
        :return: lambda client
        """
        if self._lambda_client is None:
            self._lambda_client = get_client_with_retries("lambda", ["invoke"], context=self._context)
        return self._lambda_client

    @property
    def state_table(self):
        """
        Return the name of the state table
        :return: name of the state table
        """
        return os.getenv(configuration.ENV_STATE)

    @property
    def configuration(self):
        """
        Returns the scheduler configuration
        :return: scheduler configuration
        """
        if self._configuration is None:
            self._configuration = configuration.get_scheduler_configuration(self._logger)
        return self._configuration

    def account_from_role(self, role_str):
        """
        Extracts the account name from a role arn
        :param role_str: arn of the role
        :return: account from the role, none if it is not a valid role arn
        """
        role_elements = role_str.split(":")
        if len(role_elements) < 5:
            self._logger.error(ERR_INVALID_ARN, role_str)
            return None
        return role_elements[4]

    @property
    def accounts_and_roles(self):
        """
        Iterates account and cross-account-roles of the accounts to operate on
        :return:
        """
        processed_accounts = []

        if self.configuration.schedule_lambda_account:
            processed_accounts.append(self.lambda_account)
            yield self.lambda_account

        for role in self.configuration.cross_account_roles:
            account = self.account_from_role(role)
            if account is None:
                continue
            # warn and skip if account was already processed
            if account in processed_accounts:
                self._logger.warning(WARN_DUPLICATE_ACCOUNT, account, role)
                continue
            yield role

    def account_names(self, conf):
        """
        Iterates list of accounts to process
        :param conf:
        :return:
        """
        if conf.schedule_lambda_account:
            yield self.lambda_account

        for role in conf.cross_account_roles:
            account_name = self.account_from_role(role)
            yield account_name

    @staticmethod
    def is_handling_request(event):
        """
        Handler for cloudwatch event to run the scheduler
        :return: True
        """

        return event.get("detail-type", "") == "Scheduled Event" and \
               (os.getenv(configuration.ENV_SCHEDULER_RULE)== event.get("resources", ["/"])[0].split("/")[-1])

    def _configuration_level_partitions(self, level=TOP_LEVEL):

        def service_level_configs(config):
            for service in config.scheduled_services:
                service_level_config = copy(config)
                service_level_config.scheduled_services = [service]
                yield service_level_config

        def account_level_configs(config):
            for service_level_config in service_level_configs(config):
                for account in self.accounts_and_roles:
                    account_level_config = copy(service_level_config)
                    if account is self.lambda_account:
                        account_level_config.schedule_lambda_account = True
                        account_level_config.cross_account_roles = []
                    else:
                        account_level_config.schedule_lambda_account = False
                        account_level_config.cross_account_roles = [account]
                    yield account_level_config

        def region_level_configs(config):
            for account_level_config in account_level_configs(config):
                for region in account_level_config.regions:
                    region_level_config = copy(account_level_config)
                    region_level_config.regions = [region]
                    yield region_level_config

        if level == CloudWatchEventHandler.TOP_LEVEL:
            return [self.configuration]
        elif level == CloudWatchEventHandler.SERVICE_LEVEL:
            # noinspection PyTypeChecker
            return list(service_level_configs(self.configuration))
        elif level == CloudWatchEventHandler.ACCOUNT_LEVEL:
            # noinspection PyTypeChecker
            return list(account_level_configs(self.configuration))
        else:
            # noinspection PyTypeChecker
            return list(region_level_configs(self.configuration))

    def handle_request(self):
        """
        Handles the CloudWatch Rule timer events
        :return:
        """

        def number_of_accounts():
            return len(self.configuration.cross_account_roles) + 1 if self.configuration.schedule_lambda_account else 0

        def running_as_lambda():
            return self._context is not None and not self._event.get("no_lambda", False)

        def number_of_regions():
            return max(1, len(self.configuration.regions))

        def number_of_services():
            return len(self.configuration.scheduled_services)

        try:
            self._logger.info(INF_HANDLER, self.__class__.__name__, json.dumps(self._event), datetime.now())
            if running_as_lambda():
                # running as Lambda function
                return self._run_schedulers_as_lambda(number_of_accounts, number_of_regions, number_of_services)
            else:
                # this is used to run the handler in process from an IDE
                return self._run_schedulers_in_process()
        finally:
            self._logger.flush()

    def _run_schedulers_as_lambda(self, number_of_accounts, number_of_regions, number_of_services):

        # each service/account/region combination is executed in it's own lambda instance
        level = CloudWatchEventHandler.TOP_LEVEL
        # multiple services, lambda per service
        if number_of_services() > 1:
            level = CloudWatchEventHandler.SERVICE_LEVEL
        # multiple accounts, one lambda per service/account
        if number_of_accounts() > 1:
            level = CloudWatchEventHandler.ACCOUNT_LEVEL
        # multiple regions, one lambda per service/account/region
        if number_of_regions() > 1:
            level = CloudWatchEventHandler.REGION_LEVEL
        result = []

        # partition configuration in service/account/region specific subsets and start lambda for each
        for level_configuration in self._configuration_level_partitions(level):
            # noinspection PyTypeChecker
            result.append(self._execute_as_lambda(level_configuration))
        return result

    def _run_schedulers_in_process(self):
        # local execution, used for debugging in non lambda environment and IDE's
        result = {}

        # noinspection PyTypeChecker
        account_names = list(self.account_names(self.configuration))
        self._logger.info(INF_RUN_SCHEDULER_LOCAL.format(
            ", ".join(self.configuration.scheduled_services), ", ".join(account_names),
            ", ".join(self.configuration.regions)))

        for service in self.configuration.scheduled_services:
            service_strategy = SCHEDULER_TYPES[service]()
            scheduler = InstanceScheduler(service=service_strategy, scheduler_configuration=self.configuration)
            s = "-".join([LOG_STREAM_PREFIX, "-".join(account_names), service, "-".join(self.configuration.regions)])
            dt = datetime.utcnow()
            logstream = LOG_STREAM.format(s, dt.year, dt.month, dt.day)
            with Logger(logstream=logstream, buffersize=60 if self.configuration.trace else 30, context=self._context,
                        debug=self.configuration.trace) as logger:
                result[service] = scheduler.run(state_table=self.state_table, scheduler_config=self.configuration,
                                                lambda_account=self.lambda_account, logger=logger, context=self._context)
        self._logger.info(INF_SCHEDULER_RESULT, json.dumps(result,indent=3))
        return result

    def _execute_as_lambda(self, conf):
        # runs a service/account/region subset of the configuration as a new lambda function
        self._logger.info(INF_STARTING_LAMBDA,
                          "-".join(conf.scheduled_services),
                          "-".join(self.account_names(conf)),
                          "-".join(conf.regions))

        # need to convert configuration to dictionary to allow it to be passed in event
        config = SchedulerConfigBuilder.configuration_as_dict(conf)

        payload = str.encode(json.dumps({
            "action": "scheduler:run",
            "configuration": config,
            "dispatch_time": str(datetime.now())
        }))

        if len(payload) > 200000:
            config["schedules"] = {}
            config["periods"] = {}
            payload = str.encode(json.dumps({
                "action": "scheduler:run",
                "configuration": config,
                "dispatch_time": str(datetime.now())
            }))

        # start the lambda function
        resp = self.lambda_client.invoke_with_retries(FunctionName=self._context.function_name,
                                                      InvocationType="Event", LogType="None", Payload=payload)
        if resp["StatusCode"] != 202:
            self._logger.error(ERR_STARTING_LAMBDA, self._context.function_name, self._context.function_version, config)

        result = {
            "services": list(conf.scheduled_services),
            "accounts": list(self.account_names(conf)),
            "regions": list(conf.regions),
            "lambda_invoke_result": resp["StatusCode"],
            "lambda_request_id": resp["ResponseMetadata"]["RequestId"]
        }
        return result
