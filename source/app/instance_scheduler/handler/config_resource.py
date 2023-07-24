# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import json
import re
from collections.abc import Mapping
from datetime import datetime, timezone
from re import Match
from typing import TYPE_CHECKING, Any, Literal, Optional, TypedDict, TypeGuard

import boto3

from instance_scheduler import configuration
from instance_scheduler.boto_retry import get_client_with_standard_retry
from instance_scheduler.configuration.config_admin import (
    ConfigAdmin,
    ConfigTableConfigItem,
)
from instance_scheduler.handler import setup_demo_data as demo_data
from instance_scheduler.util.app_env import get_app_env
from instance_scheduler.util.custom_resource import (
    CustomResource,
    CustomResourceRequest,
)
from instance_scheduler.util.logger import Logger

if TYPE_CHECKING:
    from aws_lambda_powertools.utilities.typing import LambdaContext
    from mypy_boto3_logs import Client as LogsClient
else:
    LambdaContext = object
    LogsClient = object

BoolStr = Literal["True", "False"]


class ServiceSetupResourceProperties(TypedDict):
    ServiceToken: str  # Lambda Function ARN
    timeout: int
    config_table: str  # DynamoDB Table name
    tagname: str  # Schedule tag key
    default_timezone: str
    use_metrics: BoolStr
    scheduled_services: list[str]
    schedule_clusters: BoolStr
    create_rds_snapshot: BoolStr
    regions: list[str]
    remote_account_ids: list[str]
    namespace: str
    aws_partition: str
    scheduler_role_name: str
    schedule_lambda_account: BoolStr
    trace: BoolStr
    enable_ssm_maintenance_windows: BoolStr
    log_retention_days: float
    started_tags: str
    stopped_tags: str
    stack_version: str
    use_aws_organizations: BoolStr


ServiceSetupRequest = CustomResourceRequest[ServiceSetupResourceProperties]


ERR_SETTING_CONFIG = "Error setting scheduler configuration {} "
ERR_SETTING_RETENTION_LAMBDA_LOGGROUP = (
    "Error setting or deleting retention period for log group {} ({})"
)

INF_CONFIG_SET = "Scheduler configuration set to {}"
INFO_DELETE_LOG_RETENTION_POLICY = (
    "Deleting log retention policy for Lambda CloudWatch loggroup {}"
)
INFO_SET_LOG_RETENTION_POLICY = (
    "Setting log retention policy for Lambda CloudWatch loggroup {} to {} days"
)

LOG_STREAM = "{}-{:0>4d}{:0>2d}{:0>2d}"


class SchedulerSetupHandler(CustomResource[ServiceSetupResourceProperties]):
    """
    Implements handler for setup helper in cloudformation
    """

    def __init__(self, event: Any, context: LambdaContext) -> None:
        CustomResource.__init__(self, event, context)
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

        self._stack_version = self.resource_properties["stack_version"]

    @staticmethod
    def is_handling_request(
        event: Mapping[str, Any]
    ) -> TypeGuard[CustomResourceRequest[ServiceSetupResourceProperties]]:
        return (
            event.get("StackId") is not None
            and event.get("ResourceType") == "Custom::ServiceSetup"
        )

    @property
    def tagname(self) -> Any:
        """
        Name of the tag to mark scheduled instances
        :return: tag name
        """
        return self.resource_properties.get(
            configuration.TAGNAME, configuration.DEFAULT_TAGNAME
        )

    @property
    def default_timezone(self) -> Any:
        """
        Returns default time zone
        :return: default timezone
        """
        return self.resource_properties.get(
            configuration.DEFAULT_TIMEZONE, configuration.DEFAULT_TZ
        )

    @property
    def use_metrics(self) -> Any:
        """
        Returns global metrics switch
        :return: metrics switch
        """
        return self.resource_properties.get(configuration.METRICS, "False")

    @property
    def trace(self) -> Any:
        """
        Returns global trace flag
        :return: trace flag
        """
        return self.resource_properties.get(configuration.TRACE, "True")

    @property
    def namespace(self) -> Any:
        """
        Returns global namespace
        :return: namespace string
        """
        return self.resource_properties.get(configuration.NAMESPACE, None)

    @property
    def aws_partition(self) -> Any:
        """
        Returns aws partition
        :return: aws partition string
        """
        return self.resource_properties.get(configuration.AWS_PARTITION, None)

    @property
    def scheduler_role_name(self) -> Any:
        """
        Returns execution_role_name
        :return: execution_role_name string
        """
        return self.resource_properties.get(configuration.SCHEDULER_ROLE_NAME, None)

    @property
    def enable_ssm_maintenance_windows(self) -> Any:
        """
        Returns global enable SSM Maintenance Windows flag
        :return: ssm_enable_ssm_maintenance_windows flag
        """
        return self.resource_properties.get(
            configuration.ENABLE_SSM_MAINTENANCE_WINDOWS, "False"
        )

    @property
    def regions(self) -> set[str] | list[str]:
        """
        Returns all regions from the configuration
        :return: regions
        """
        result: set[str] | list[str] = set(self.resource_properties["regions"])
        if result == set() or len([i for i in result if i.strip() != ""]) == 0:
            result = [boto3.Session().region_name]
        return result

    @property
    def started_tags(self) -> Any:
        """
        Returns started tags as a string
        :return: started tags
        """
        return self.resource_properties.get(configuration.STARTED_TAGS, None)

    @property
    def stopped_tags(self) -> Any:
        """
        Returns stopped tags as a string
        :return: stopped tags
        """
        return self.resource_properties.get(configuration.STOPPED_TAGS, None)

    @property
    def remote_account_ids(self) -> Any:
        """
        Returns remote account ids
        :return: remote account ids
        """
        result = set(self.resource_properties["remote_account_ids"])
        if result == set() or len([i for i in result if i.strip() != ""]) == 0:
            return None

        return result

    @property
    def old_remote_account_ids(self) -> Any:
        """
        Returns remote account ids from the previous event of create/update
        :return: remote account ids
        """
        result = set(self.old_resource_properties["remote_account_ids"])
        if result == set() or len([i for i in result if i.strip() != ""]) == 0:
            return None

        return result

    @property
    def scheduled_services(self) -> Optional[set[str]]:
        """
        Returns scheduled services
        :return: services to schedule
        """
        result = set(self.resource_properties["scheduled_services"])
        if result == set() or len([i for i in result if i.strip() != ""]) == 0:
            return None

        return result

    @property
    def schedule_clusters(self) -> Any:
        """
        Returns global schedule clusters flag
        :return: schedule_clusters flag
        """
        return self.resource_properties.get(configuration.SCHEDULE_CLUSTERS, "False")

    @property
    def create_rds_snapshot(self) -> Any:
        """
        Returns global create RDS Snapshots flag
        :return: create_rds_snapshot flag
        """
        return self.resource_properties.get(configuration.CREATE_RDS_SNAPSHOT, "True")

    @property
    def schedule_lambda_account(self) -> Any:
        """
        Returns flag for processing lambda account switch
        :return: lambda account process switch
        """
        return self.resource_properties.get(
            configuration.SCHEDULE_LAMBDA_ACCOUNT, "True"
        )

    @property
    def use_aws_organizations(self) -> Any:
        """
        Returns use_aws_organizations flag
        :return: use_aws_organizations flag
        """
        return self.resource_properties.get(
            configuration.USE_AWS_ORGANIZATIONS, "False"
        )

    def handle_request(self) -> None:
        """
        Handles the custom resource request to write scheduler global settings to config database
        :return:
        """

        try:
            self._logger.info(
                "Handler {} : Received request {}",
                self.__class__.__name__,
                json.dumps(self.event),
            )
            CustomResource.handle_request(self)
        finally:
            self._logger.flush()

    def get_valid_org_id(self, org_id: str) -> Optional[Match[str]]:
        """
        Verifies if the ou_id param is a valid ou_id format. https://docs.aws.amazon.com/organizations/latest/APIReference/API_Organization.html
        :return: the org id or else None
        """
        return re.fullmatch("^o-[a-z0-9]{10,32}$", org_id)

    def _update_settings(self, prev_org_remote_account_ids: Any = None) -> bool:
        if prev_org_remote_account_ids is None:
            prev_org_remote_account_ids = {}

        try:
            admin = ConfigAdmin(logger=self._logger, context=self.context)
            try:
                org_id = list(self.remote_account_ids)[0]
            except Exception as error:
                self._logger.info(f"org id is not valid or empty {error}")
                org_id = ""

            if self.get_valid_org_id(org_id) and self.use_aws_organizations == "True":
                self.organization_id = org_id
                remote_account_ids = prev_org_remote_account_ids
            elif (
                self.get_valid_org_id(org_id) and self.use_aws_organizations == "False"
            ):
                self.organization_id = org_id
                remote_account_ids = {}
            else:
                self.organization_id = ""
                remote_account_ids = self.remote_account_ids

            settings = admin.update_config(
                ConfigTableConfigItem(
                    default_timezone=self.default_timezone,
                    scheduled_services=self.scheduled_services or set(),
                    schedule_clusters=self.schedule_clusters,
                    create_rds_snapshot=self.create_rds_snapshot,
                    tagname=self.tagname,
                    regions=self.regions,
                    remote_account_ids=remote_account_ids,
                    organization_id=self.organization_id,
                    schedule_lambda_account=self.schedule_lambda_account.lower()
                    == "true",
                    use_metrics=self.use_metrics.lower() == "true",
                    trace=self.trace.lower() == "true",
                    enable_ssm_maintenance_windows=self.enable_ssm_maintenance_windows.lower()
                    == "true",
                    scheduler_role_name=self.scheduler_role_name,
                    aws_partition=self.aws_partition,
                    namespace=self.namespace,
                    started_tags=self.started_tags,
                    stopped_tags=self.stopped_tags,
                )
            )

            self._logger.info(INF_CONFIG_SET, str(settings))

        except Exception as ex:
            self._logger.info(ERR_SETTING_CONFIG, ex)
            return False

        return True

    def set_lambda_logs_retention_period(self) -> None:
        """
        Sets the retention period of the log group associated with the Lambda context to
        - resource_properties["log_retention_days"] if present
        - default value of 30 otherwise
        """
        if not self.context:
            return

        loggroup: str = self.context.log_group_name
        log_client: LogsClient = get_client_with_standard_retry("logs")
        retention_days = int(self.resource_properties.get("log_retention_days", 30))
        try:
            self._logger.info(INFO_SET_LOG_RETENTION_POLICY, loggroup, retention_days)
            log_client.put_retention_policy(
                logGroupName=loggroup, retentionInDays=int(retention_days)
            )
        except Exception as ex:
            self._logger.warning(
                ERR_SETTING_RETENTION_LAMBDA_LOGGROUP,
                self.context.log_group_name,
                str(ex),
            )

    def _create_sample_schemas(self) -> None:
        try:
            admin: ConfigAdmin = ConfigAdmin(logger=self._logger, context=self.context)

            admin.create_period(demo_data.PERIOD_WORKING_DAYS)
            admin.create_period(demo_data.PERIOD_WEEKENDS)
            admin.create_period(demo_data.PERIOD_OFFICE_HOURS)
            admin.create_period(demo_data.PERIOD_FIRST_MONDAY_IN_QUARTER)

            admin.create_schedule(demo_data.SCHEDULE_SEATTLE_OFFICE_HOURS)
            admin.create_schedule(demo_data.SCHEDULE_UK_OFFICE_HOURS)
            admin.create_schedule(demo_data.SCHEDULE_STOPPED)
            admin.create_schedule(demo_data.SCHEDULE_RUNNING)
            admin.create_schedule(demo_data.SCHEDULE_SCALING)

        except Exception as ex:
            self._logger.error(
                "Error creating sample schedules and periods {}".format(ex)
            )

    # handles Create request from CloudFormation
    def _create_request(self) -> bool:
        self._create_sample_schemas()
        result = self._update_settings()
        self.set_lambda_logs_retention_period()
        return result

    def _update_request(self) -> bool:
        try:
            org_id = list(self.remote_account_ids)[0]
        except Exception as error:
            self._logger.info(f"org id is not valid or empty {error}")
            org_id = ""
        try:
            prev_org_id = list(self.old_remote_account_ids)[0]
        except Exception as error:
            self._logger.info(
                f"org id from old custom resource request parameters is not valid or empty {error}"
            )
            prev_org_id = ""
        if (
            self.get_valid_org_id(org_id)
            and self.get_valid_org_id(prev_org_id)
            and org_id == prev_org_id
        ):
            config = configuration.get_global_configuration(self._logger)
            prev_remote_account_id = config.remote_account_ids
        else:
            prev_remote_account_id = []
        result = self._update_settings(prev_remote_account_id)
        self.set_lambda_logs_retention_period()
        return result

    # handles Delete request from CloudFormation
    def _delete_request(self) -> bool:
        return True
