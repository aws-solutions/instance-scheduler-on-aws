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
from copy import copy
from datetime import datetime
from hashlib import sha256

import boto3

import configuration
import requesthandlers.setup_demo_data as demo_data
from boto_retry import get_client_with_retries
from configuration.config_admin import ConfigAdmin
from util.custom_resource import CustomResource
from util.logger import Logger
from util.metrics import allow_send_metrics, send_metrics_data

ERR_SETTING_CONFIG = "Error setting scheduler configuration {} "
ERR_SETTING_RETENTION_LAMBDA_LOGGROUP = "Error setting or deleting retention period for log group {} ({})"

INF_CONFIG_SET = "Scheduler configuration set to {}"
INFO_DELETE_LOG_RETENTION_POLICY = "Deleting log retention policy for Lambda CloudWatch loggroup {}"
INFO_SET_LOG_RETENTION_POLICY = "Setting log retention policy for Lambda CloudWatch loggroup {} to {} days"

LOG_STREAM = "{}-{:0>4d}{:0>2d}{:0>2d}"


class SchedulerSetupHandler(CustomResource):
    """
    Implements handler for setup helper in cloudformation
    """

    def __init__(self, event, context):

        CustomResource.__init__(self, event, context)
        # Setup logging
        classname = self.__class__.__name__
        dt = datetime.utcnow()
        log_stream = LOG_STREAM.format(classname, dt.year, dt.month, dt.day)
        self._logger = Logger(logstream=log_stream, buffersize=1, context=context)

        self.arguments = copy(self.resource_properties)
        self.arguments = {a: self.resource_properties[a] for a in self.resource_properties if a not in ["ServiceToken",
                                                                                                        "Timeout"]}

        self._stack_version = self.arguments["stack_version"]

    @staticmethod
    def is_handling_request(event):
        return event.get("StackId") is not None and event.get("ResourceType") == "Custom::ServiceSetup"

    @property
    def tagname(self):
        """
        Name of the tag to mark scheduled instances
        :return: tag name
        """
        return self.resource_properties.get(configuration.TAGNAME, configuration.DEFAULT_TAGNAME)

    @property
    def default_timezone(self):
        """
        Returns default time zone
        :return: default timezone
        """
        return self.resource_properties.get(configuration.DEFAULT_TIMEZONE, configuration.DEFAULT_TZ)

    @property
    def use_metrics(self):
        """
        Returns global metrics switch
        :return: metrics switch
        """
        return self.resource_properties.get(configuration.METRICS, "False")

    @property
    def trace(self):
        """
        Returns global trace flag
        :return: trace flag
        """
        return self.resource_properties.get(configuration.TRACE, "True")

    @property
    def regions(self):
        """
        Returns all regions from the configuration
        :return: regions
        """
        result = set(self.resource_properties.get(configuration.REGIONS))
        if result is None or result == set() or len([i for i in result if i.strip() != ""]) == 0:
            result = [boto3.Session().region_name]
        return result

    @property
    def started_tags(self):
        """
        Returns started tags as a string
        :return: started tags
        """
        return self.resource_properties.get(configuration.STARTED_TAGS, None)

    @property
    def stopped_tags(self):
        """
        Returns stopped tags as a string
        :return: stopped tags
        """
        return self.resource_properties.get(configuration.STOPPED_TAGS, None)

    @property
    def cross_account_roles(self):
        """
        Returns cross-account roles
        :return: cross account roles
        """
        result = set(self.resource_properties.get(configuration.CROSS_ACCOUNT_ROLES))
        if result is None or result == set() or len([i for i in result if i.strip() != ""]) == 0:
            return None

        return result

    @property
    def scheduled_services(self):
        """
        Returns scheduled services
        :return: services to schedule
        """
        result = set(self.resource_properties.get(configuration.SCHEDULED_SERVICES))
        if result is None or result == set() or len([i for i in result if i.strip() != ""]) == 0:
            return None

        return result

    @property
    def schedule_clusters(self):
        """
        Returns global trace flag
        :return: trace flag
        """
        return self.resource_properties.get(configuration.SCHEDULE_CLUSTERS, "False")

    @property
    def create_rds_snapshot(self):
        """
        Returns global trace flag
        :return: trace flag
        """
        return self.resource_properties.get(configuration.CREATE_RDS_SNAPSHOT, "True")

    @property
    def schedule_lambda_account(self):
        """
        Returns flag for processing lambda account switch
        :return: lambda account process switch
        """
        return self.resource_properties.get(configuration.SCHEDULE_LAMBDA_ACCOUNT, "True")

    def handle_request(self):
        """
        Handles the custom resource request to write scheduler global settings to config database
        :return:
        """

        try:
            self._logger.info("Handler {} : Received request {}", self.__class__.__name__, json.dumps(self.event))
            CustomResource.handle_request(self)
        finally:
            self._logger.flush()

    def _update_settings(self):
        try:
            admin = ConfigAdmin(logger=self._logger, context=self.context)
            settings = admin.update_config(default_timezone=self.default_timezone,
                                           scheduled_services=self.scheduled_services,
                                           schedule_clusters=self.schedule_clusters,
                                           create_rds_snapshot = self.create_rds_snapshot,
                                           tagname=self.tagname,
                                           regions=self.regions,
                                           cross_account_roles=self.cross_account_roles,
                                           schedule_lambda_account=self.schedule_lambda_account.lower() == "true",
                                           use_metrics=self.use_metrics.lower() == "true",
                                           trace=self.trace.lower() == "true",
                                           started_tags=self.started_tags,
                                           stopped_tags=self.stopped_tags)

            self._logger.info(INF_CONFIG_SET, str(settings))

        except Exception as ex:
            self._logger.info(ERR_SETTING_CONFIG, ex)
            return False

        return True

    def set_lambda_logs_retention_period(self):
        """
        Aligns retention period for default Lambda log streams with settings
        :return:
        """

        if self.context is None:
            return True

        loggroup = self.context.log_group_name
        log_client = get_client_with_retries("logs", ["delete_retention_policy", "put_retention_policy"], context=self.context)
        retention_days = self.arguments.get("log_retention_days", 30)
        try:
            if retention_days is None:
                self._logger.info(INFO_DELETE_LOG_RETENTION_POLICY, loggroup)
                log_client.delete_retention_policy_with_retries(loggroup)
                return True
            else:
                self._logger.info(INFO_SET_LOG_RETENTION_POLICY, loggroup, retention_days)
                log_client.put_retention_policy_with_retries(logGroupName=loggroup, retentionInDays=int(retention_days))
                return True
        except Exception as ex:
            self._logger.warning(ERR_SETTING_RETENTION_LAMBDA_LOGGROUP, self.context.log_group_name, str(ex))
            return True

    def _create_sample_schemas(self):

        try:
            admin = ConfigAdmin(logger=self._logger, context=self.context)

            admin.create_period(**demo_data.PERIOD_WORKING_DAYS)
            admin.create_period(**demo_data.PERIOD_WEEKENDS)
            admin.create_period(**demo_data.PERIOD_OFFICE_HOURS)
            admin.create_period(**demo_data.PERIOD_FIRST_MONDAY_IN_QUARTER)

            admin.create_schedule(**demo_data.SCHEDULE_SEATTLE_OFFICE_HOURS)
            admin.create_schedule(**demo_data.SCHEDULE_UK_OFFICE_HOURS)
            admin.create_schedule(**demo_data.SCHEDULE_STOPPED)
            admin.create_schedule(**demo_data.SCHEDULE_RUNNING)
            admin.create_schedule(**demo_data.SCHEDULE_SCALING)

        except Exception as ex:
            self._logger.error("Error creating sample schedules and periods {}".format(ex))

    def _send_create_metrics(self):
        metrics_data = {
            "Type": "stack",
            "Version": self._stack_version,
            "StackHash": sha256(self.stack_id.encode('utf-8')).hexdigest(),
            "Data": {
                "Status": "stack_create",
                "Region": self.region
            }
        }

        send_metrics_data(metrics=metrics_data, logger=self._logger)

    def _send_delete_metrics(self):

        metrics_data = {
            "Type": "stack",
            "Version": self._stack_version,
            "StackHash": sha256(self.stack_id.encode('utf-8')).hexdigest(),
            "Data": {
                "Status": "stack_delete",
                "Region": self.region
            }
        }

        send_metrics_data(metrics=metrics_data, logger=self._logger)

    # handles Create request from CloudFormation
    def _create_request(self):
        if allow_send_metrics():
            self._send_create_metrics()
        self._create_sample_schemas()
        return self._update_settings() and self.set_lambda_logs_retention_period()

    def _update_request(self):
        return self._update_settings() and self.set_lambda_logs_retention_period()

    # handles Delete request from CloudFormation
    def _delete_request(self):
        if allow_send_metrics():
            self._send_delete_metrics()
        return True
