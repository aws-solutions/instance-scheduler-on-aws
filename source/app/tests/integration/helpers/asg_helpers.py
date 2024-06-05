# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import json
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from typing import TYPE_CHECKING, Any, Final, cast
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

from boto3 import client
from botocore.exceptions import ClientError
from moto.core.models import DEFAULT_ACCOUNT_ID

from instance_scheduler.handler.asg import ASG_SERVICE
from instance_scheduler.handler.scheduling_request import SchedulingRequest
from instance_scheduler.model.period_definition import PeriodDefinition
from instance_scheduler.model.period_identifier import PeriodIdentifier
from instance_scheduler.model.schedule_definition import ScheduleDefinition
from instance_scheduler.model.store.dynamo_period_definition_store import (
    DynamoPeriodDefinitionStore,
)
from instance_scheduler.model.store.dynamo_schedule_definition_store import (
    DynamoScheduleDefinitionStore,
)
from instance_scheduler.ops_metrics.metric_type.asg_count_metric import AsgCountMetric
from instance_scheduler.service.asg import AsgSize, AsgTag
from tests import DEFAULT_REGION
from tests.conftest import get_ami

if TYPE_CHECKING:
    from mypy_boto3_autoscaling.client import AutoScalingClient
    from mypy_boto3_autoscaling.type_defs import ScheduledUpdateGroupActionTypeDef
    from mypy_boto3_ec2.client import EC2Client
    from mypy_boto3_ecs.client import ECSClient
else:
    AutoScalingClient = object
    ScheduledUpdateGroupActionTypeDef = object
    EC2Client = object
    ECSClient = object


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


def create_simple_schedule(
    *,
    config_table_name: str,
    schedule_name: str,
    begin_time: time,
    end_time: time,
    time_zone: ZoneInfo | None = None,
    monthdays: set[str] | None = None,
) -> None:
    schedule_store: Final = DynamoScheduleDefinitionStore(table_name=config_table_name)
    period_store: Final = DynamoPeriodDefinitionStore(table_name=config_table_name)

    period_name: Final = f"{schedule_name}-period"
    period: Final = PeriodDefinition(
        name=period_name,
        begintime=begin_time.strftime("%H:%M"),
        endtime=end_time.strftime("%H:%M"),
        monthdays=monthdays,
    )
    period_store.put(period)

    schedule: Final = ScheduleDefinition(
        name=schedule_name,
        periods=[PeriodIdentifier.of(period_name)],
        timezone=str(time_zone) if time_zone else None,
    )
    schedule_store.put(schedule)


def get_or_create_launch_template() -> str:
    ec2: Final[EC2Client] = client("ec2")
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


def get_az_name() -> str:
    ec2: Final[EC2Client] = client("ec2")
    zones: Final = ec2.describe_availability_zones()
    if len(zones["AvailabilityZones"]) == 0:
        raise AsgTestError("No availability zones")
    return zones["AvailabilityZones"][0]["ZoneName"]


def create_asg(group_name: str, running_size: AsgSize) -> None:
    autoscaling: Final[AutoScalingClient] = client("autoscaling")
    autoscaling.create_auto_scaling_group(
        AutoScalingGroupName=group_name,
        MinSize=running_size.min_size,
        DesiredCapacity=running_size.desired_size,
        MaxSize=running_size.max_size,
        LaunchTemplate={"LaunchTemplateName": get_or_create_launch_template()},
        AvailabilityZones=[get_az_name()],
    )


def tag_group(*, group_name: str, tag_key: str, tag_value: str) -> None:
    autoscaling: Final[AutoScalingClient] = client("autoscaling")
    autoscaling.create_or_update_tags(
        Tags=[
            {
                "ResourceType": "auto-scaling-group",
                "ResourceId": group_name,
                "Key": tag_key,
                "Value": tag_value,
                "PropagateAtLaunch": False,
            }
        ]
    )


def get_actions(group_name: str) -> Iterator[ScheduledUpdateGroupActionTypeDef]:
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


def add_actions(group_name: str, asg_size: AsgSize, schedule: ScheduleHelper) -> None:
    autoscaling: Final[AutoScalingClient] = client("autoscaling")
    autoscaling.batch_put_scheduled_update_group_action(
        AutoScalingGroupName=group_name,
        ScheduledUpdateGroupActions=[
            {
                "ScheduledActionName": f"{RULE_PREFIX}{schedule.name}-periodStart",
                "Recurrence": schedule.start_recurrence,
                "MinSize": asg_size.min_size,
                "MaxSize": asg_size.max_size,
                "DesiredCapacity": asg_size.desired_size,
                "TimeZone": str(schedule.time_zone),
            },
            {
                "ScheduledActionName": f"{RULE_PREFIX}{schedule.name}-periodStop",
                "Recurrence": schedule.end_recurrence,
                "MinSize": 0,
                "MaxSize": 0,
                "DesiredCapacity": 0,
                "TimeZone": str(schedule.time_zone),
            },
        ],
    )


def get_actions_for_schedule(
    group_name: str, schedule: ScheduleHelper, running_size: AsgSize
) -> Iterator[ScheduledUpdateGroupActionTypeDef]:
    if schedule.time_zone is None:
        raise AsgTestError("Need time zone to find actions")

    actions: Final = list(get_actions(group_name))
    yield find_action(
        actions, running_size, schedule.start_recurrence, schedule.time_zone
    )
    yield find_action(
        actions, AsgSize.stopped(), schedule.end_recurrence, schedule.time_zone
    )


def get_tag_value(*, group_name: str, tag_key: str) -> str:
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
        ScheduledActionNames=list(
            action["ScheduledActionName"]
            for action in actions["ScheduledUpdateGroupActions"]
        ),
    )
    if len(response["FailedScheduledActions"]) > 0:
        raise AsgTestError("Failed to delete some actions")


def get_scheduled_tag(group_name: str) -> AsgTag:
    tag_value: Final = json.loads(
        get_tag_value(group_name=group_name, tag_key=ASG_SCHEDULED_TAG_KEY)
    )

    return AsgTag(
        schedule=tag_value["schedule"],
        ttl=tag_value["ttl"],
        min_size=tag_value["min_size"],
        max_size=tag_value["max_size"],
        desired_size=tag_value["desired_size"],
    )


def create_ecs_cluster_with_auto_scaling(
    ecs_asg_group_name: str, running_size: AsgSize
) -> None:
    create_asg(group_name=ecs_asg_group_name, running_size=running_size)
    ecs: Final[ECSClient] = client("ecs")
    ecs.create_cluster(clusterName="MyCluster", capacityProviders=[ecs_asg_group_name])


def verify_operational_metrics(
    mock_collect_metric: MagicMock, should_send_metrics: bool
) -> None:
    if should_send_metrics:
        assert mock_collect_metric.call_count == 1
        instance_count_metric = mock_collect_metric.call_args[1].get("metric")
        assert instance_count_metric == AsgCountMetric(
            service=ASG_SERVICE, region=DEFAULT_REGION, num_instances=1, num_schedules=1
        )
    else:
        assert mock_collect_metric.call_count == 0

    mock_collect_metric.reset_mock()


def verify_scheduled_actions_and_tagged(
    asg_group_name: str, schedule: ScheduleHelper, asg_size: AsgSize, dt: datetime
) -> None:
    num_scheduled_actions: Final = len(
        list(get_actions_for_schedule(asg_group_name, schedule, asg_size))
    )
    assert num_scheduled_actions == 2

    tag: Final[AsgTag] = get_scheduled_tag(asg_group_name)
    assert tag == AsgTag(
        schedule=schedule.name,
        ttl=(dt + timedelta(days=30)).isoformat(),
        min_size=asg_size.min_size,
        max_size=asg_size.max_size,
        desired_size=asg_size.desired_size,
    )


def build_lambda_event(
    dt: datetime, schedule_names: list[str] | None
) -> dict[str, Any]:
    if schedule_names:
        scheduling_request = SchedulingRequest(
            action="scheduler:run",
            account=DEFAULT_ACCOUNT_ID,
            region=DEFAULT_REGION,
            service=ASG_SERVICE,
            current_dt=dt.isoformat(),
            dispatch_time=dt.isoformat(),
            schedule_names=schedule_names,
        )
    else:
        scheduling_request = SchedulingRequest(
            action="scheduler:run",
            account=DEFAULT_ACCOUNT_ID,
            region=DEFAULT_REGION,
            service=ASG_SERVICE,
            current_dt=dt.isoformat(),
            dispatch_time=dt.isoformat(),
        )

    return cast(dict[str, Any], scheduling_request)
