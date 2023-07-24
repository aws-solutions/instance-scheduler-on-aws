# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from typing import Optional

import boto3
from mypy_boto3_ec2.client import EC2Client
from mypy_boto3_ec2.type_defs import (
    DescribeInstancesResultTypeDef,
    DescribeInstanceStatusResultTypeDef,
    TagTypeDef,
)

from instance_scheduler.configuration.instance_schedule import InstanceSchedule
from tests import ami
from tests.integration.helpers.boto_client_helpers import client_in_account_region


def create_ec2_instances(
    count: int,
    schedule: InstanceSchedule,
    account: str = "123456789012",
    region: str = "us-east-1",
) -> tuple[str, ...]:
    ec2_client: EC2Client = client_in_account_region("ec2", account, region)
    create_response = ec2_client.run_instances(
        ImageId=ami, MinCount=count, MaxCount=count
    )
    instance_ids = [instance["InstanceId"] for instance in create_response["Instances"]]
    ec2_client.create_tags(
        Resources=instance_ids, Tags=[{"Key": "Schedule", "Value": schedule.name}]
    )

    return tuple(instance_ids)


def get_current_state(instance_id: str, ec2_client: Optional[EC2Client] = None) -> str:
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


def get_tags(instance_id: str) -> list[TagTypeDef]:
    ec2_client: EC2Client = boto3.client("ec2")
    describe_response: DescribeInstancesResultTypeDef = ec2_client.describe_instances(
        InstanceIds=[instance_id]
    )

    return describe_response["Reservations"][0]["Instances"][0]["Tags"]
