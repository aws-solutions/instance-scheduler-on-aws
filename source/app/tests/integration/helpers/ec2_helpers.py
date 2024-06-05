# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from typing import Optional

import boto3
from mypy_boto3_ec2.client import EC2Client
from mypy_boto3_ec2.literals import InstanceStateNameType, InstanceTypeType
from mypy_boto3_ec2.type_defs import (
    DescribeInstancesResultTypeDef,
    DescribeInstanceStatusResultTypeDef,
    TagTypeDef,
)

from tests.conftest import get_ami
from tests.integration.helpers.boto_client_helpers import client_in_account_region


def create_ec2_instances(
    count: int,
    schedule_name: str,
    account: str = "123456789012",
    region: str = "us-east-1",
    instance_type: InstanceTypeType = "t2.micro",
) -> tuple[str, ...]:
    ec2_client: EC2Client = client_in_account_region("ec2", account, region)
    create_response = ec2_client.run_instances(
        ImageId=get_ami(region),
        MinCount=count,
        MaxCount=count,
        InstanceType=instance_type,
    )
    instance_ids = [instance["InstanceId"] for instance in create_response["Instances"]]
    ec2_client.create_tags(
        Resources=instance_ids, Tags=[{"Key": "Schedule", "Value": schedule_name}]
    )

    return tuple(instance_ids)


def stop_ec2_instances(
    *instance_ids: str,
    account: str = "123456789012",
    region: str = "us-east-1",
) -> None:
    ec2_client: EC2Client = client_in_account_region("ec2", account, region)
    ec2_client.stop_instances(InstanceIds=instance_ids)


def start_ec2_instances(
    *instance_ids: str,
    account: str = "123456789012",
    region: str = "us-east-1",
) -> None:
    ec2_client: EC2Client = client_in_account_region("ec2", account, region)
    ec2_client.start_instances(InstanceIds=instance_ids)


def get_current_state(
    instance_id: str, ec2_client: Optional[EC2Client] = None
) -> InstanceStateNameType:
    client: EC2Client
    if ec2_client:
        client = ec2_client
    else:
        client = boto3.client("ec2")
    describe_response: DescribeInstanceStatusResultTypeDef = (
        client.describe_instance_status(
            InstanceIds=[instance_id], IncludeAllInstances=True
        )
    )

    return describe_response["InstanceStatuses"][0]["InstanceState"]["Name"]


def get_current_instance_type(
    instance_id: str, ec2_client: Optional[EC2Client] = None
) -> str:
    client: EC2Client
    if ec2_client:
        client = ec2_client
    else:
        client = boto3.client("ec2")
    return client.describe_instances(InstanceIds=[instance_id])["Reservations"][0][
        "Instances"
    ][0]["InstanceType"]


def get_tags(instance_id: str) -> list[TagTypeDef]:
    ec2_client: EC2Client = boto3.client("ec2")
    describe_response: DescribeInstancesResultTypeDef = ec2_client.describe_instances(
        InstanceIds=[instance_id]
    )

    return describe_response["Reservations"][0]["Instances"][0]["Tags"]
