# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from typing import Any

import boto3
from mypy_boto3_sts import STSClient


def client_in_account_region(
    client: str, account: str, region: str = "us-east-1"
) -> Any:
    sts: STSClient = boto3.client("sts")
    token = sts.assume_role(
        RoleArn=f"arn:aws:iam::{account}:role/moto-role",
        RoleSessionName="create-instances-session",
        ExternalId="create-instances-external-id",
    )["Credentials"]

    return boto3.client(
        client,
        aws_access_key_id=token["AccessKeyId"],
        aws_secret_access_key=token["SecretAccessKey"],
        aws_session_token=token["SessionToken"],
        region_name=region,
    )
