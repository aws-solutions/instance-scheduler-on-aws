# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from dataclasses import dataclass
from functools import cache
from os import environ
from typing import TYPE_CHECKING, Any, Final, Optional

import boto3
from boto3 import Session
from botocore.config import Config as _Config
from botocore.exceptions import ClientError

if TYPE_CHECKING:
    from mypy_boto3_dynamodb import DynamoDBClient
    from mypy_boto3_sts.client import STSClient
else:
    STSClient = object
    DynamoDBClient = object


def get_boto_config() -> _Config:
    """Returns a boto3 config with standard retries and `user_agent_extra`"""
    return _Config(
        retries={"max_attempts": 10, "mode": "standard"},
        user_agent_extra=environ[
            "USER_AGENT_EXTRA"
        ],  # todo: don't access environ directly here (need better validation for USER_AGENT_EXTRA existing)
    )


def _sts() -> STSClient:
    session: Final = Session()
    if session.get_partition_for_region(session.region_name) == "aws-cn":
        sts_regional_endpoint = str.format(
            "https://sts.{}.amazonaws.com.cn", session.region_name
        )
    else:
        sts_regional_endpoint = str.format(
            "https://sts.{}.amazonaws.com", session.region_name
        )

    sts_client: STSClient = session.client(
        "sts",
        region_name=session.region_name,
        endpoint_url=sts_regional_endpoint,
        config=get_boto_config(),
    )

    return sts_client


def get_role_arn(*, account_id: str, role_name: str) -> str:
    session = boto3.Session()
    partition = session.get_partition_for_region(session.region_name)

    return ":".join(
        [
            "arn",
            partition,
            "iam",
            "",
            account_id,
            f"role/{role_name}",
        ]
    )


@dataclass(frozen=True)
class AssumedRole:
    session: Session
    role_name: str
    account: str
    region: str

    @property
    def partition(self) -> str:
        return self.session.get_partition_for_region(self.region)

    def client(self, service_name: str, region: Optional[str] = None) -> Any:
        """simple wrapper for session.client() that includes the default config from get_boto_config"""
        if region:
            return self.session.client(service_name, region, config=get_boto_config())
        else:
            return self.session.client(
                service_name, region_name=self.region, config=get_boto_config()
            )


def assume_role(*, account: str, region: str, role_name: str) -> AssumedRole:
    spoke_account_role_arn: Final = get_role_arn(
        account_id=account, role_name=role_name
    )

    try:
        # session name has a max length of 64
        role_name_space = 64 - len(f"-{account}-{region}")
        session_name: Final = f"{role_name[:role_name_space]}-{account}-{region}"

        token: Final = _sts().assume_role(
            RoleArn=spoke_account_role_arn, RoleSessionName=session_name
        )

        credentials: Final = token["Credentials"]

        session = Session(
            aws_access_key_id=credentials["AccessKeyId"],
            aws_secret_access_key=credentials["SecretAccessKey"],
            aws_session_token=credentials["SessionToken"],
            region_name=region,
        )

        return AssumedRole(
            session=session,
            account=account,
            region=region,
            role_name=role_name,
        )
    except ClientError as ex:
        """rethrow"""
        raise ex


@cache
def lambda_execution_role() -> AssumedRole:
    """
    Get the execution role for the lambda function
    """
    session = boto3.Session()
    return AssumedRole(
        session=session,
        account=session.client("sts").get_caller_identity()["Account"],
        region=session.region_name,
        role_name="",
    )


@cache
def hub_dynamo_client() -> DynamoDBClient:
    client: DynamoDBClient = lambda_execution_role().client("dynamodb")
    return client
