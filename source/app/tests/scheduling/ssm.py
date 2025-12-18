# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from typing import TYPE_CHECKING, Final, List, Literal, Optional

from botocore.exceptions import ClientError
from instance_scheduler.observability.powertools_logging import (
    powertools_logger,
)
from instance_scheduler.util.session_manager import assume_role, lambda_execution_role

if TYPE_CHECKING:
    from mypy_boto3_ssm.client import SSMClient
    from mypy_boto3_ssm.type_defs import (
        GetParametersByPathResultTypeDef,
        ParameterTypeDef,
        PutParameterResultTypeDef,
    )
else:
    SSMClient = object
    GetParametersByPathResultTypeDef = object
    ParameterTypeDef = object
    PutParameterResultTypeDef = object

logger: Final = powertools_logger()


class SSMService:
    def __init__(
        self,
        account_id: Optional[str] = None,
        region: Optional[str] = None,
        role_name: Optional[str] = None,
    ) -> None:
        if account_id and region and role_name:
            assumed_role = assume_role(
                account=account_id,
                region=region,
                role_name=role_name,
            )
        else:
            assumed_role = lambda_execution_role()
        self._ssm_client: Final[SSMClient] = assumed_role.client("ssm")
        self._logger: Final = logger

    def put_parameter(
        self,
        name: str,
        value: str,
        parameter_type: Literal["SecureString", "String", "StringList"] = "String",
        tier: Literal["Advanced", "Intelligent-Tiering", "Standard"] = "Advanced",
        overwrite: bool = True,
    ) -> None:

        self._ssm_client.put_parameter(
            Name=name,
            Value=value,
            Type=parameter_type,
            Tier=tier,
            Overwrite=overwrite,
        )

    def delete_parameter(self, name: str) -> None:
        try:
            self._ssm_client.delete_parameter(Name=name)
        except ClientError as error:
            self._logger.error(f"Error deleting parameter {error}")
            if error.response["Error"]["Code"] != "ParameterNotFound":
                raise error

    def get_parameters_by_path(self, path: str) -> List[ParameterTypeDef]:
        response: GetParametersByPathResultTypeDef = (
            self._ssm_client.get_parameters_by_path(Path=path)
        )
        parameters: List[ParameterTypeDef] = response["Parameters"]
        next_token: Optional[str] = response.get("NextToken", None)

        while next_token is not None:
            response = self._ssm_client.get_parameters_by_path(
                Path=path, NextToken=next_token
            )
            parameters.extend(response["Parameters"])
            next_token = response.get("NextToken", None)

        return parameters
