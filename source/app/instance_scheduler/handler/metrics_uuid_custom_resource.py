# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import uuid
from typing import TYPE_CHECKING, Any, Mapping, Optional, TypedDict

import boto3
from botocore.exceptions import ClientError

from instance_scheduler.handler.environments.metrics_uuid_environment import (
    MetricsUuidEnvironment,
)
from instance_scheduler.util import get_boto_config
from instance_scheduler.util.custom_resource import (
    CustomResource,
    CustomResourceResponse,
)

if TYPE_CHECKING:
    from aws_lambda_powertools.utilities.typing import LambdaContext
    from mypy_boto3_ssm import SSMClient
else:
    LambdaContext = object
    SSMClient = object


class CreateUuidRequest(TypedDict):
    pass  # empty dict, no values are provided


def handle_metrics_uuid_request(
    event: Mapping[str, Any], context: LambdaContext
) -> Any:
    handler = MetricsUuidCustomResource(
        event, context, MetricsUuidEnvironment.from_env()
    )
    return handler.handle_request()


class MetricsUuidCustomResource(CustomResource[CreateUuidRequest]):
    """
    custom resource for generating a unique metrics id for the solution

    for backwards-compatibility with previous versions (<=1.5.3), this custom resource checks for a metrics-uuid value
    already being present in SSM and will return that uuid value instead of generating a new one
    """

    def __init__(self, event: Any, context: LambdaContext, env: MetricsUuidEnvironment):
        self._env = env
        CustomResource.__init__(self, event, context)

    def _create_request(self) -> CustomResourceResponse:
        metrics_uuid = self._get_metrics_uuid_from_ssm_if_exists()
        if not metrics_uuid:
            metrics_uuid = uuid.uuid4()

        return self.OkResponse(data={"Uuid": str(metrics_uuid)})

    def _update_request(self) -> CustomResourceResponse:
        return self.ErrorResponse(
            reason="Updates for this resource type are not supported"
        )

    def _delete_request(self) -> CustomResourceResponse:
        return self.OkResponse()  # nothing to do

    def _get_metrics_uuid_from_ssm_if_exists(self) -> Optional[uuid.UUID]:
        stack_id = self._env.stack_id[-36:]
        uuid_key = self._env.uuid_key + str(stack_id)
        ssm: SSMClient = boto3.client("ssm", config=get_boto_config())
        try:
            ssm_response = ssm.get_parameter(Name=uuid_key)
            uuid_parameter = ssm_response.get("Parameter", {}).get("Value")
            return uuid.UUID(uuid_parameter)
        except ClientError:
            return None
