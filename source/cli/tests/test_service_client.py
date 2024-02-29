# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from typing import TYPE_CHECKING

from moto import mock_aws

from instance_scheduler_cli.scheduler_cli import _service_client

if TYPE_CHECKING:
    from mypy_boto3_cloudformation import CloudFormationClient
else:
    CloudFormationClient = object


def test_service_client() -> None:
    with mock_aws():
        client: CloudFormationClient = _service_client("cloudformation")
        assert client.describe_stacks()["Stacks"] == []
