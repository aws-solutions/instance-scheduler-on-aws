# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from contextlib import contextmanager
from typing import Any, Iterator
from unittest.mock import MagicMock, patch

import boto3
from instance_scheduler.util.session_manager import AssumedRole
from mypy_boto3_sts import STSClient


def assume_mocked_role(
    account: str = "123456789012", region: str = "us-east-1"
) -> AssumedRole:
    sts: STSClient = boto3.client("sts")
    token = sts.assume_role(
        RoleArn=f"arn:aws:iam::{account}:role/moto-role",
        RoleSessionName="create-instances-session",
        ExternalId="create-instances-external-id",
    )["Credentials"]

    return AssumedRole(
        session=boto3.Session(
            aws_access_key_id=token["AccessKeyId"],
            aws_secret_access_key=token["SecretAccessKey"],
            aws_session_token=token["SessionToken"],
            region_name=region,
        ),
        account=account,
        region=region,
        role_name=f"mocked-moto-role-{account}-{region}",
    )


@contextmanager
def mock_specific_client(
    client_name: str, region: str = "us-east-1"
) -> Iterator[MagicMock]:
    # clear cache before mocking the client to ensure caches dont get in the way of the mock
    # todo: delete this
    # AssumedRole.client.cache_clear()

    real_client = boto3.client(client_name, region_name=region)
    mock_client = MagicMock(wraps=real_client)
    original_client_func = boto3.Session().client

    def selectively_mock_client(service_name: str, **kwargs: Any) -> Any:
        if service_name == client_name and kwargs.get("region_name") == region:
            return mock_client
        return original_client_func(service_name, **kwargs)

    with patch("boto3.Session.client", side_effect=selectively_mock_client):
        yield mock_client
