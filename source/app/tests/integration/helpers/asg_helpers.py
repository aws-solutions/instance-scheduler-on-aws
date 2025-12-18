# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Final, Optional
from zoneinfo import ZoneInfo

from boto3 import client
from botocore.exceptions import ClientError
from instance_scheduler.model.schedule_definition import ScheduleDefinition
from instance_scheduler.scheduling.asg.asg_runtime_info import AsgRuntimeInfo
from instance_scheduler.scheduling.asg.asg_size import AsgSize
from instance_scheduler.util.session_manager import AssumedRole, lambda_execution_role
from tests.conftest import get_ami

if TYPE_CHECKING:
    from mypy_boto3_autoscaling.client import AutoScalingClient
    from mypy_boto3_autoscaling.type_defs import (
        AutoScalingGroupTypeDef,
        ScheduledUpdateGroupActionTypeDef,
    )
    from mypy_boto3_ec2.client import EC2Client
    from mypy_boto3_ecs.client import ECSClient
else:
    AutoScalingClient = object
    ScheduledUpdateGroupActionTypeDef = object
    EC2Client = object
    ECSClient = object
    AutoScalingGroupTypeDef = object


ASG_GROUP_NAME: Final = "my-group"
ASG_SCHEDULED_TAG_KEY: Final = "scheduled"
RULE_PREFIX: Final = "is-"
SCHEDULE_TAG_KEY: Final = "Schedule"
TEST_DATETIME: Final = datetime(year=2024, month=2, day=28, tzinfo=timezone.utc)


class AsgTestError(Exception):
    pass


@dataclass(frozen=True)
class ScheduleHelper:
    name: str
    start_recurrence: str
    end_recurrence: str
    time_zone: ZoneInfo | None


def get_or_create_launch_template(assumed_role: AssumedRole) -> str:
    ec2: Final[EC2Client] = assumed_role.client("ec2")
    template_name: Final = "my-template"
    try:
        ec2.describe_launch_templates(LaunchTemplateNames=[template_name])
    except ClientError as err:
        if (
            err.response["Error"]["Code"]
            == "InvalidLaunchTemplateName.NotFoundException"
        ):
            ec2.create_launch_template(
                LaunchTemplateName=template_name,
                LaunchTemplateData={"ImageId": get_ami()},
            )
        else:
            raise

    return template_name


def get_subnet_id(role: Optional[AssumedRole] = None) -> str:
    if not role:
        role = lambda_execution_role()
    ec2: Final[EC2Client] = role.client("ec2")

    # Get default VPC
    vpcs = ec2.describe_vpcs(Filters=[{"Name": "is-default", "Values": ["true"]}])
    if not vpcs["Vpcs"]:
        raise AsgTestError("No default VPC found")

    vpc_id = vpcs["Vpcs"][0]["VpcId"]

    # Get subnets in the default VPC
    subnets = ec2.describe_subnets(Filters=[{"Name": "vpc-id", "Values": [vpc_id]}])
    if not subnets["Subnets"]:
        raise AsgTestError("No subnets found in default VPC")

    return subnets["Subnets"][0]["SubnetId"]


def create_asg(
    group_name: str,
    running_size: AsgSize,
    schedule: ScheduleDefinition | str | None,
    role: Optional[AssumedRole] = None,
) -> AsgRuntimeInfo:
    if not role:
        role = lambda_execution_role()
    if isinstance(schedule, ScheduleDefinition):
        schedule = schedule.name

    autoscaling: Final[AutoScalingClient] = role.client("autoscaling")
    autoscaling.create_auto_scaling_group(
        AutoScalingGroupName=group_name,
        MinSize=running_size.min_size,
        DesiredCapacity=running_size.desired_size,
        MaxSize=running_size.max_size,
        LaunchTemplate={"LaunchTemplateName": get_or_create_launch_template(role)},
        VPCZoneIdentifier=get_subnet_id(role),
    )

    if schedule:
        autoscaling.create_or_update_tags(
            Tags=[
                {
                    "ResourceType": "auto-scaling-group",
                    "ResourceId": group_name,
                    "Key": "Schedule",
                    "Value": schedule,
                    "PropagateAtLaunch": False,
                }
            ]
        )

    # Return the actual ASG group object
    response = autoscaling.describe_auto_scaling_groups(
        AutoScalingGroupNames=[group_name]
    )
    return AsgRuntimeInfo(response["AutoScalingGroups"][0])


def get_asg(group_name: str) -> "AutoScalingGroupTypeDef":
    autoscaling: Final[AutoScalingClient] = client("autoscaling")
    response = autoscaling.describe_auto_scaling_groups(
        AutoScalingGroupNames=[group_name]
    )
    return response["AutoScalingGroups"][0]


def set_mdm_tag(asg: str, size: Optional[AsgSize]) -> None:
    autoscaling: Final[AutoScalingClient] = client("autoscaling")
    if size:
        autoscaling.create_or_update_tags(
            Tags=[
                {
                    "ResourceType": "auto-scaling-group",
                    "ResourceId": asg,
                    "Key": "IS-MinDesiredMax",
                    "Value": size.to_mdm_str(),
                    "PropagateAtLaunch": False,
                }
            ]
        )
    else:
        autoscaling.delete_tags(
            Tags=[
                {
                    "ResourceType": "auto-scaling-group",
                    "ResourceId": asg,
                    "Key": "IS-MinDesiredMax",
                }
            ]
        )


def get_configured_actions(
    group_name: str,
) -> Iterator[ScheduledUpdateGroupActionTypeDef]:
    autoscaling: Final[AutoScalingClient] = client("autoscaling")
    paginator: Final = autoscaling.get_paginator("describe_scheduled_actions")
    for page in paginator.paginate(AutoScalingGroupName=group_name):
        yield from page["ScheduledUpdateGroupActions"]


def find_action(
    actions: Iterable[ScheduledUpdateGroupActionTypeDef],
    size: AsgSize,
    recurrence: str,
    time_zone: ZoneInfo,
) -> ScheduledUpdateGroupActionTypeDef:
    matches: Final = list(
        filter(
            lambda action: action["MinSize"] == size.min_size
            and action["DesiredCapacity"] == size.desired_size
            and action["MaxSize"] == size.max_size
            and action["Recurrence"] == recurrence
            and action["TimeZone"] == str(time_zone),
            actions,
        )
    )
    if len(matches) == 0:
        raise AsgTestError("No matching action")
    return matches[0]


def get_actions_for_schedule(
    group_name: str, schedule: ScheduleHelper, running_size: AsgSize
) -> Iterator[ScheduledUpdateGroupActionTypeDef]:
    if schedule.time_zone is None:
        raise AsgTestError("Need time zone to find actions")

    actions: Final = list(get_configured_actions(group_name))
    yield find_action(
        actions, running_size, schedule.start_recurrence, schedule.time_zone
    )
    yield find_action(
        actions, AsgSize.stopped(), schedule.end_recurrence, schedule.time_zone
    )


def get_tag_value(group_name: str, tag_key: str) -> str:
    autoscaling: Final[AutoScalingClient] = client("autoscaling")
    desc: Final = autoscaling.describe_auto_scaling_groups(
        AutoScalingGroupNames=[group_name]
    )
    if len(desc["AutoScalingGroups"]) == 0:
        raise AsgTestError("Group not found")
    matches: Final = list(
        filter(lambda tag: tag["Key"] == tag_key, desc["AutoScalingGroups"][0]["Tags"])
    )
    if len(matches) == 0:
        raise KeyError("No tag found")
    return matches[0]["Value"]


def delete_all_actions(group_name: str) -> None:
    autoscaling: Final[AutoScalingClient] = client("autoscaling")
    actions: Final = autoscaling.describe_scheduled_actions(
        AutoScalingGroupName=group_name
    )
    response: Final = autoscaling.batch_delete_scheduled_action(
        AutoScalingGroupName=group_name,
        ScheduledActionNames=[
            action["ScheduledActionName"]
            for action in actions["ScheduledUpdateGroupActions"]
        ],
    )
    if len(response["FailedScheduledActions"]) > 0:
        raise AsgTestError("Failed to delete some actions")


def create_ecs_cluster_with_auto_scaling(
    ecs_asg_group_name: str, running_size: AsgSize
) -> None:
    create_asg(group_name=ecs_asg_group_name, running_size=running_size, schedule=None)
    ecs: Final[ECSClient] = client("ecs")
    ecs.create_cluster(clusterName="MyCluster", capacityProviders=[ecs_asg_group_name])
