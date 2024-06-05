# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Iterator
from unittest.mock import MagicMock, patch

from _pytest.fixtures import fixture
from freezegun import freeze_time
from mypy_boto3_ec2 import EC2Client
from mypy_boto3_ec2.literals import InstanceTypeType
from mypy_boto3_rds import RDSClient

from instance_scheduler.ops_monitoring.cw_ops_insights import (
    CloudWatchOperationalInsights,
)
from tests.conftest import get_ami
from tests.integration.helpers.boto_client_helpers import client_in_account_region
from tests.integration.helpers.ec2_helpers import (
    create_ec2_instances,
    start_ec2_instances,
    stop_ec2_instances,
)
from tests.integration.helpers.run_handler import simple_schedule
from tests.integration.helpers.schedule_helpers import quick_time
from tests.test_utils.mock_scheduling_request_environment import (
    MockSchedulingRequestEnvironment,
)
from tests.test_utils.unordered_list import UnorderedList

if TYPE_CHECKING:
    from mypy_boto3_rds.type_defs import CreateDBInstanceResultTypeDef
else:
    CreateDBInstanceResultTypeDef = object

# ec2 instance types
small: InstanceTypeType = "t2.micro"
medium: InstanceTypeType = "t2.medium"
large: InstanceTypeType = "t2.large"


def rds_instance(
    account: str, region: str, instance_type: str = "db.m5.large", stop: bool = False
) -> str:
    instance_id = "rds-test-instance"
    rds_client: RDSClient = client_in_account_region("rds", account, region)
    result = new_rds_instances_of_type(rds_client, instance_type, instance_id)
    instance_arn = result["DBInstance"]["DBInstanceArn"]
    rds_client.add_tags_to_resource(
        ResourceName=instance_arn, Tags=[{"Key": "Schedule", "Value": "test-schedule"}]
    )
    if stop:
        rds_client.stop_db_instance(DBInstanceIdentifier=instance_id)

    return instance_id


def new_rds_instances_of_type(
    rds_client: RDSClient, rds_instance_type: str, instance_id: str
) -> CreateDBInstanceResultTypeDef:
    result: CreateDBInstanceResultTypeDef = rds_client.create_db_instance(
        DBInstanceIdentifier=instance_id,
        DBInstanceClass=rds_instance_type,
        Engine="postgres",
    )

    return result


def create_test_instances(
    count: int,
    instance_type: InstanceTypeType,
    account: str,
    region: str,
    stop: bool = False,
) -> list[str]:
    ec2_client: EC2Client = client_in_account_region("ec2", account, region)
    instance_ids = new_ec2_instances_of_type(ec2_client, count, instance_type)
    ec2_client.create_tags(
        Resources=instance_ids, Tags=[{"Key": "Schedule", "Value": "test-schedule"}]
    )

    if stop:
        ec2_client.stop_instances(InstanceIds=instance_ids)

    return instance_ids


def new_ec2_instances_of_type(
    ec2_client: EC2Client, count: int, ec2_instance_type: InstanceTypeType
) -> list[str]:
    create_response = ec2_client.run_instances(
        ImageId=get_ami(),
        MinCount=count,
        MaxCount=count,
        InstanceType=ec2_instance_type,
    )
    instance_ids = [instance["InstanceId"] for instance in create_response["Instances"]]

    return instance_ids


@fixture
def mocked_put_metric_data() -> Iterator[MagicMock]:
    with patch.object(
        CloudWatchOperationalInsights, "cloudwatch_client"
    ) as cloudwatch_client:
        with patch.object(cloudwatch_client, "put_metric_data") as put_metric_func:
            yield put_metric_func


def test_metrics_not_sent_when_disabled(
    state_table: str,
    mocked_put_metric_data: MagicMock,
) -> None:
    with simple_schedule(begintime="10:00", endtime="20:00") as context:
        context.run_scheduling_request_handler(
            dt=quick_time(12, 0),
            environment=MockSchedulingRequestEnvironment(enable_ops_monitoring=False),
        )

    mocked_put_metric_data.assert_not_called()


@freeze_time("2023-12-28 20:23:37")
def test_ops_monitoring_metrics_sent_to_cw_when_enabled(
    state_table: str,
    mocked_put_metric_data: MagicMock,
) -> None:
    stop_ec2_instances(
        *create_ec2_instances(1, instance_type=small, schedule_name="test-schedule")
    )
    start_ec2_instances(
        *create_ec2_instances(5, instance_type=medium, schedule_name="test-schedule")
    )

    with simple_schedule(begintime="10:00", endtime="20:00") as context:
        context.run_scheduling_request_handler(
            dt=quick_time(12, 0),
            environment=MockSchedulingRequestEnvironment(enable_ops_monitoring=True),
        )

    fixed_time = datetime(2023, 12, 28, 20, 23, 37, tzinfo=timezone.utc)
    expected_metric_data = {
        "Namespace": "my-stack-name:InstanceScheduler",
        "MetricData": UnorderedList(
            [
                # per schedule data
                {
                    "MetricName": "ManagedInstances",
                    "Dimensions": [
                        {"Name": "Service", "Value": "ec2"},
                        {"Name": "Schedule", "Value": "test-schedule"},
                        {"Name": "SchedulingInterval", "Value": "5"},
                    ],
                    "Timestamp": fixed_time,
                    "Value": 6,
                    "Unit": "Count",
                },
                {
                    "MetricName": "RunningInstances",
                    "Dimensions": [
                        {"Name": "Service", "Value": "ec2"},
                        {"Name": "Schedule", "Value": "test-schedule"},
                        {"Name": "SchedulingInterval", "Value": "5"},
                    ],
                    "Timestamp": fixed_time,
                    "Value": 5,
                    "Unit": "Count",
                },
                # per instance_type data
                {
                    "MetricName": "ManagedInstances",
                    "Dimensions": [
                        {"Name": "Service", "Value": "ec2"},
                        {"Name": "InstanceType", "Value": "t2.micro"},
                        {"Name": "SchedulingInterval", "Value": "5"},
                    ],
                    "Timestamp": fixed_time,
                    "Value": 1,
                    "Unit": "Count",
                },
                {
                    "MetricName": "RunningInstances",
                    "Dimensions": [
                        {"Name": "Service", "Value": "ec2"},
                        {"Name": "InstanceType", "Value": "t2.micro"},
                        {"Name": "SchedulingInterval", "Value": "5"},
                    ],
                    "Timestamp": fixed_time,
                    "Value": 0,
                    "Unit": "Count",
                },
                {
                    "MetricName": "StoppedInstances",
                    "Dimensions": [
                        {"Name": "Service", "Value": "ec2"},
                        {"Name": "InstanceType", "Value": "t2.micro"},
                        {"Name": "SchedulingInterval", "Value": "5"},
                    ],
                    "Timestamp": fixed_time,
                    "Value": 1,
                    "Unit": "Count",
                },
                {
                    "MetricName": "ManagedInstances",
                    "Dimensions": [
                        {"Name": "Service", "Value": "ec2"},
                        {"Name": "InstanceType", "Value": "t2.medium"},
                        {"Name": "SchedulingInterval", "Value": "5"},
                    ],
                    "Timestamp": fixed_time,
                    "Value": 5,
                    "Unit": "Count",
                },
                {
                    "MetricName": "RunningInstances",
                    "Dimensions": [
                        {"Name": "Service", "Value": "ec2"},
                        {"Name": "InstanceType", "Value": "t2.medium"},
                        {"Name": "SchedulingInterval", "Value": "5"},
                    ],
                    "Timestamp": fixed_time,
                    "Value": 5,
                    "Unit": "Count",
                },
                {
                    "MetricName": "StoppedInstances",
                    "Dimensions": [
                        {"Name": "Service", "Value": "ec2"},
                        {"Name": "InstanceType", "Value": "t2.medium"},
                        {"Name": "SchedulingInterval", "Value": "5"},
                    ],
                    "Timestamp": fixed_time,
                    "Value": 0,
                    "Unit": "Count",
                },
            ]
        ),
    }

    args, kwargs = mocked_put_metric_data.call_args
    assert kwargs == expected_metric_data
    mocked_put_metric_data.assert_called_once()
