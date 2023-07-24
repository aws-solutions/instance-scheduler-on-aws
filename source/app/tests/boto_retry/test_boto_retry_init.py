# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from typing import TYPE_CHECKING

from moto import mock_ec2

from instance_scheduler.boto_retry import get_client_with_standard_retry

if TYPE_CHECKING:
    from mypy_boto3_ec2.client import EC2Client
else:
    EC2Client = object


def test_get_client_with_standard_retry() -> None:
    with mock_ec2():
        client: EC2Client = get_client_with_standard_retry("ec2")
        assert client.describe_instances()["Reservations"] == []
