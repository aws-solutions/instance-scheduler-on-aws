# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

import boto3
from boto3 import Session
from botocore.exceptions import ClientError

from instance_scheduler.util import get_boto_config

if TYPE_CHECKING:
    from mypy_boto3_sts.client import STSClient
else:
    STSClient = object


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

    def client(self, service_name: str) -> Any:
        """simple wrapper for session.client() that includes the default config from get_boto_config"""
        return self.session.client(service_name, config=get_boto_config())


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
