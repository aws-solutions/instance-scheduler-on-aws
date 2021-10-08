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

import re
import os
import json
import boto3
import configuration
import requesthandlers.setup_demo_data as demo_data
from copy import copy
from datetime import datetime
from hashlib import sha256
from configuration.config_admin import ConfigAdmin
from util.custom_resource import CustomResource
from util import get_config
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
    def trace(self):
        """
        Returns global trace flag
        :return: trace flag
        """
        return self.resource_properties.get(configuration.TRACE, "True")

        
    @property
    def namespace(self):
        """
        Returns global namepsace
        :return: namespace string
        """
        return self.resource_properties.get(configuration.NAMEPSACE, None)

    @property
    def aws_partition(self):
        """
        Returns aws partition
        :return: aws partition string
        """
        return self.resource_properties.get(configuration.AWS_PARTITION, None)

    @property
    def execution_role_name(self):
        """
        Returns execution_role_name
        :return: execution_role_name string
        """
        return self.resource_properties.get(configuration.EXECUTION_ROLE_NAME, None)

    @property
    def regions(self):
        """
        Returns all regions from the configuration
        :return: regions
        """
        result = set(self.resource_properties.get(configuration.REGIONS))
        if result == set() or len([i for i in result if i.strip() != ""]) == 0:
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
    def remote_account_ids(self):
        """
        Returns remote account ids
        :return: remote account ids
        """
        result = set(self.resource_properties.get(configuration.REMOTE_ACCOUNT_IDS))
        if result == set() or len([i for i in result if i.strip() != ""]) == 0:
            return None

        return result
    
    @property
    def old_remote_account_ids(self):
        """
        Returns remote account ids from the previous event of create/update
        :return: remote account ids
        """
        result = set(self.old_resource_properties.get(configuration.REMOTE_ACCOUNT_IDS))
        if result == set() or len([i for i in result if i.strip() != ""]) == 0:
            return None

        return result

    @property
    def scheduled_services(self):
        """
        Returns scheduled services
        :return: services to schedule
        """
        result = set(self.resource_properties.get(configuration.SCHEDULED_SERVICES))
        if result == set() or len([i for i in result if i.strip() != ""]) == 0:
            return None

        return result

    @property
    def schedule_clusters(self):
        """
        Returns global schedule clusters flag
        :return: schedule_clusters flag
        """
        return self.resource_properties.get(configuration.SCHEDULE_CLUSTERS, "False")

    @property
    def create_rds_snapshot(self):
        """
        Returns global create RDS Snapshots flag
        :return: create_rds_snapshot flag
        """
        return self.resource_properties.get(configuration.CREATE_RDS_SNAPSHOT, "False")

    @property
    def use_aws_organizations(self):
        """
        Returns use_aws_organizations flag
        :return: use_aws_organizations flag
        """
        return self.resource_properties.get(configuration.USE_AWS_ORGANIZATIONS, "False")

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

    def is_valid_org_id(self, org_id):
        """
        Verifies if the ou_id param is a valid ou_id format. https://docs.aws.amazon.com/organizations/latest/APIReference/API_Organization.html
        :return: boolean
        """
        try:
            return re.fullmatch("^o-[a-z0-9]{10,32}$", org_id)
        except Exception as error:
            raise error

    def _update_settings(self, prev_org_remote_account_ids={os.getenv(configuration.ENV_ACCOUNT)}):
        try:
            admin = ConfigAdmin(logger=self._logger, context=self.context)
            try: 
                org_id = list(self.remote_account_ids)[0]
            except Exception as error:
                self._logger.info(f"org id is not valid or empty {error}")
                org_id = ""

            if self.is_valid_org_id(org_id) and self.use_aws_organizations == "True":
                self.organization_id = org_id
                remote_account_ids = prev_org_remote_account_ids
            elif self.is_valid_org_id(org_id) and self.use_aws_organizations == "False":
                self.organization_id = org_id
                remote_account_ids = {}
            else:
                self.organization_id = ""
                remote_account_ids = self.remote_account_ids

            settings = admin.update_config(default_timezone=self.default_timezone,
                                           scheduled_services=self.scheduled_services,
                                           schedule_clusters=self.schedule_clusters,
                                           create_rds_snapshot = self.create_rds_snapshot,
                                           tagname=self.tagname,
                                           regions=self.regions,
                                           remote_account_ids=remote_account_ids,
                                           organization_id=self.organization_id,
                                           trace=self.trace.lower() == "true",
                                           namespace=self.namespace,
                                           execution_role_name=self.execution_role_name,
                                           aws_partition=self.aws_partition,
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
        try:
            loggroup = self.context.log_group_name
            log_client = boto3.client("logs", config=get_config())
            retention_days = self.arguments.get("log_retention_days", 30)
            if retention_days is None:
                self._logger.info(INFO_DELETE_LOG_RETENTION_POLICY, loggroup)
                log_client.delete_retention_policy(loggroup)
            else:
                self._logger.info(INFO_SET_LOG_RETENTION_POLICY, loggroup, retention_days)
                log_client.put_retention_policy(logGroupName=loggroup, retentionInDays=int(retention_days))
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
        try:
            org_id = list(self.remote_account_ids)[0]
        except Exception as error:
            self._logger.info(f"org id is not valid or empty {error}")
            org_id = ""
        try:
            prev_org_id = list(self.old_remote_account_ids)[0]
        except Exception as error:
            self._logger.info(f"org id from old custom resource request parameters is not valid or empty {error}")
            prev_org_id = ""
        if self.is_valid_org_id(org_id) and self.is_valid_org_id(prev_org_id) and org_id == prev_org_id:
            config = configuration.get_scheduler_configuration(self._logger)
            prev_remote_account_id = config.remote_account_ids
        else:
            solution_account = os.getenv(configuration.ENV_ACCOUNT)
            prev_remote_account_id = {solution_account}
        return self._update_settings(prev_remote_account_id) and self.set_lambda_logs_retention_period()

    # handles Delete request from CloudFormation
    def _delete_request(self):
        if allow_send_metrics():
            self._send_delete_metrics()
        return True
