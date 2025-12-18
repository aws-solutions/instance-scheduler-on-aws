# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import json
from typing import TYPE_CHECKING, Any, Final, List, Mapping, TypedDict

from aws_lambda_powertools import Logger
from instance_scheduler.handler.environments.region_registration_environment import (
    RegionRegistrationEnvironment,
)
from instance_scheduler.handler.region_registration_events_handler import (
    RegionRegistrationState,
)
from instance_scheduler.handler.service.ssm import SSMService
from instance_scheduler.observability.powertools_logging import (
    powertools_logger,
    should_log_events,
)
from instance_scheduler.util.custom_resource_waiter import (
    CustomResourceWaiter,
    CustomResourceWaiterResponse,
)
from instance_scheduler.util.session_manager import (
    lambda_execution_role,
)
from urllib3 import PoolManager

if TYPE_CHECKING:
    from aws_lambda_powertools.utilities.typing import LambdaContext
    from mypy_boto3_ssm.type_defs import (
        ParameterTypeDef,
    )
else:
    LambdaContext = object
    ParameterTypeDef = object

http = PoolManager()

logger: Final = powertools_logger()


@logger.inject_lambda_context(log_event=should_log_events(logger))
def lambda_handler(event: Mapping[str, Any], context: LambdaContext) -> Any:
    try:
        env = RegionRegistrationEnvironment.from_env()
        handler = RegionRegistrationIsCompleteHandler(event, context, logger, env)
        return handler.handle_request()
    except Exception as error:
        logger.error(
            f"Error occurred while running custom resource lambda with error {error}"
        )
        response_body = {
            "Status": "FAILED",
            "Reason": f"Custom resource failed with error: {error}",
            "PhysicalResourceId": event.get("LogicalResourceId"),
            "StackId": event.get("StackId"),
            "RequestId": event.get("RequestId"),
            "LogicalResourceId": event.get("LogicalResourceId"),
        }

        headers = {"Content-Type": "application/json"}
        http.request(
            "PUT",
            event.get("ResponseURL", ""),
            headers=headers,
            body=json.dumps(response_body),
        )


class RegionRegistrationIsCompleteProperties(TypedDict):
    regions: List[str]


class RegionRegistrationIsCompleteHandler(
    CustomResourceWaiter[RegionRegistrationIsCompleteProperties]
):
    def __init__(
        self,
        event: Any,
        context: LambdaContext,
        logger: Logger,
        env: RegionRegistrationEnvironment,
    ) -> None:
        super().__init__(event, context)
        self._logger: Final = logger
        self._env: Final = env

    def _get_ssm_parameters(self) -> List[ParameterTypeDef]:
        ssm_service = SSMService()
        return ssm_service.get_parameters_by_path(path=f"{self._env.ssm_param_path}/")

    def _create_request(self) -> CustomResourceWaiterResponse:
        parameters: List[ParameterTypeDef] = self._get_ssm_parameters()
        for parameter in parameters:
            parameter_value: str = parameter["Value"]

            if parameter_value != RegionRegistrationState.MANAGED.value:
                return self.OkResponse(is_complete=False)

        # delete the params before sending the ok response
        for parameter in parameters:
            ssm_service = SSMService()
            ssm_service.delete_parameter(name=parameter["Name"])
        return self.OkResponse(is_complete=True)

    def _update_request(self) -> CustomResourceWaiterResponse:
        current_regions = self.purge_empty_strings(self.resource_properties, "regions")
        if not current_regions:
            current_regions.append(lambda_execution_role().region)

        old_regions = self.purge_empty_strings(self.old_resource_properties, "regions")
        if not old_regions:
            old_regions.append(lambda_execution_role().region)

        delete_regions = list(set(old_regions) - set(current_regions))

        region_status = {}
        for region in current_regions:
            region_status[region] = RegionRegistrationState.MANAGED.value

        for region in delete_regions:
            region_status[region] = RegionRegistrationState.DELETED.value
        parameters: List[ParameterTypeDef] = self._get_ssm_parameters()

        for parameter in parameters:
            parameter_value: str = parameter["Value"]
            parameter_name: str = parameter["Name"]
            region = parameter_name.split("/")[4]
            if region_status.get(region) != parameter_value:
                return self.OkResponse(is_complete=False)

        # delete the params before sending the ok response
        for parameter in parameters:
            ssm_service = SSMService(region=region)
            ssm_service.delete_parameter(name=parameter["Name"])

        return self.OkResponse(is_complete=True)

    def _delete_request(self) -> CustomResourceWaiterResponse:
        regions = self.purge_empty_strings(self.resource_properties, "regions")
        if not regions:
            regions = [lambda_execution_role().region]

        parameters: List[ParameterTypeDef] = self._get_ssm_parameters()
        for parameter in parameters:
            parameter_value: str = parameter["Value"]
            if parameter_value != RegionRegistrationState.DELETED.value:
                return self.OkResponse(is_complete=False)

        for region in regions:
            ssm_service = SSMService(region=region)
            ssm_service.delete_parameter(name=f"{self._env.ssm_param_path}/{region}")
        return self.OkResponse(is_complete=True)
