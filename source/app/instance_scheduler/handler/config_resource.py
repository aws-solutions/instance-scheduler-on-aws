# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import json
import re
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, TypedDict, TypeGuard

from instance_scheduler.boto_retry import get_client_with_standard_retry
from instance_scheduler.handler import setup_demo_data as demo_data
from instance_scheduler.handler.environments.main_lambda_environment import (
    MainLambdaEnv,
)
from instance_scheduler.model.ddb_config_item import DdbConfigItem
from instance_scheduler.model.store.ddb_config_item_store import DdbConfigItemStore
from instance_scheduler.model.store.dynamo_period_definition_store import (
    DynamoPeriodDefinitionStore,
)
from instance_scheduler.model.store.dynamo_schedule_definition_store import (
    DynamoScheduleDefinitionStore,
)
from instance_scheduler.util.custom_resource import (
    CustomResource,
    CustomResourceRequest,
    CustomResourceResponse,
)
from instance_scheduler.util.logger import Logger

if TYPE_CHECKING:
    from aws_lambda_powertools.utilities.typing import LambdaContext
    from mypy_boto3_logs import Client as LogsClient
else:
    LambdaContext = object
    LogsClient = object


class ServiceSetupResourceProperties(TypedDict):
    timeout: int
    remote_account_ids: list[str]
    log_retention_days: float


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


class SchedulerSetupHandler(CustomResource[ServiceSetupResourceProperties]):
    """
    Implements handler for setup helper in cloudformation
    """

    def __init__(self, event: Any, context: LambdaContext, env: MainLambdaEnv) -> None:
        self._env = env
        CustomResource.__init__(self, event, context)
        self.config_item_store = DdbConfigItemStore(env.config_table_name)

        # Setup logging
        classname = self.__class__.__name__
        dt = datetime.now(timezone.utc)
        log_stream = "{}-{:0>4d}{:0>2d}{:0>2d}".format(
            classname, dt.year, dt.month, dt.day
        )
        self._logger = Logger(
            log_group=env.log_group,
            log_stream=log_stream,
            topic_arn=env.topic_arn,
            debug=env.enable_debug_logging,
        )

    @staticmethod
    def is_handling_request(
        event: Mapping[str, Any]
    ) -> TypeGuard[CustomResourceRequest[ServiceSetupResourceProperties]]:
        return (
            event.get("StackId") is not None
            and event.get("ResourceType") == "Custom::ServiceSetup"
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

    def set_lambda_logs_retention_period(self) -> None:
        """
        Sets the retention period of the log group associated with the Lambda context to
        - resource_properties["log_retention_days"] if present
        - default value of 30 otherwise
        """
        # note: this only updates the log retention of the Main lambda
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
            period_store = DynamoPeriodDefinitionStore(self._env.config_table_name)
            schedule_store = DynamoScheduleDefinitionStore(self._env.config_table_name)

            for demo_period in demo_data.DEMO_PERIODS:
                period_store.put(demo_period)

            for demo_schedule in demo_data.DEMO_SCHEDULES:
                schedule_store.put(demo_schedule)

        except Exception as ex:
            self._logger.error(
                "Error creating sample schedules and periods {}".format(ex)
            )

    # handles Create request from CloudFormation
    def _create_request(self) -> CustomResourceResponse:
        self._create_sample_schemas()
        self.set_lambda_logs_retention_period()
        if self._env.enable_aws_organizations:
            org_id = parse_as_org_id(self.resource_properties)
            self.config_item_store.put(
                DdbConfigItem(organization_id=org_id, remote_account_ids=[])
            )
        else:
            spoke_accounts = parse_as_account_ids(self.resource_properties)
            self.config_item_store.put(
                DdbConfigItem(organization_id="", remote_account_ids=spoke_accounts)
            )
        return self.OkResponse()

    def _update_request(self) -> CustomResourceResponse:
        """
        Scenarios to Handle:
        when orgs not enabled:
        -always overwrite accounts
        when orgs enabled:
        -when org_id does not change -- keep accounts
        -when org_id does change -- purge accounts
        """
        if self._env.enable_aws_organizations:
            # using organizations
            try:
                prev_org_id = parse_as_org_id(self.old_resource_properties)
            except ValueError:
                prev_org_id = ""
            org_id = parse_as_org_id(self.resource_properties)

            if org_id == prev_org_id:
                self._logger.info(
                    "org_id has not changed, preserving registered spoke accounts..."
                )
                spoke_accounts = self.config_item_store.get().remote_account_ids
                self._logger.info(
                    f"preserved {len(spoke_accounts)} registered spoke accounts"
                )
            else:
                self._logger.info(
                    f"org_id has not changed from {prev_org_id} to {org_id}, "
                    f"registered spoke accounts will not be preserved"
                )
                spoke_accounts = []

            self.config_item_store.put(
                DdbConfigItem(organization_id=org_id, remote_account_ids=spoke_accounts)
            )
        else:
            # not using organizations
            spoke_accounts = parse_as_account_ids(self.resource_properties)
            self.config_item_store.put(
                DdbConfigItem(organization_id="", remote_account_ids=spoke_accounts)
            )

        return self.OkResponse()

    # handles Delete request from CloudFormation
    def _delete_request(self) -> CustomResourceResponse:
        # no action to taken
        return self.OkResponse()


def parse_as_org_id(props: ServiceSetupResourceProperties) -> str:
    ids_list = props["remote_account_ids"]
    if len(ids_list) != 1:
        raise ValueError(
            f"org_id must be provided as a single value! received: {ids_list}"
        )
    org_id = props["remote_account_ids"][0]
    if not is_org_id(org_id):
        raise ValueError(f"invalid org id {org_id}")
    return org_id


def parse_as_account_ids(props: ServiceSetupResourceProperties) -> list[str]:
    return props["remote_account_ids"]


def is_org_id(org_id: str) -> bool:
    """
    Verifies if the ou_id param is a valid ou_id format. https://docs.aws.amazon.com/organizations/latest/APIReference/API_Organization.html
    :return: the org id or else None
    """
    return bool(re.fullmatch("^o-[a-z0-9]{10,32}$", org_id))
