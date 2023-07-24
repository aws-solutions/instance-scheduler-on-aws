# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import json
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import boto3
from aws_lambda_powertools.utilities.typing import LambdaContext

from instance_scheduler.handler.config_resource import (
    SchedulerSetupHandler,
    ServiceSetupResourceProperties,
)
from instance_scheduler.util.app_env import AppEnv
from instance_scheduler.util.custom_resource import CustomResourceRequest

if TYPE_CHECKING:
    from mypy_boto3_dynamodb.client import DynamoDBClient
else:
    DynamoDBClient = object


@patch("custom_resource.requests")
class CustomResourceLambdaContext(LambdaContext):
    def __init__(self) -> None:
        LambdaContext.__init__(self)
        self._log_group_name = "my-log-group"

    @staticmethod
    def get_remaining_time_in_millis() -> int:
        return 1000 * 60 * 15


def resource_properties(
    org_id: str, config_table_name: str
) -> ServiceSetupResourceProperties:
    return ServiceSetupResourceProperties(
        ServiceToken="lambda-arn",
        timeout=120,
        config_table=config_table_name,
        tagname="Schedule",
        default_timezone="UTC",
        use_metrics="False",
        scheduled_services=["ec2"],
        schedule_clusters="False",
        create_rds_snapshot="False",
        regions=["us-east-1"],
        remote_account_ids=[org_id],
        namespace="test",
        aws_partition="aws",
        scheduler_role_name="scheduler-role",
        schedule_lambda_account="False",
        trace="False",
        enable_ssm_maintenance_windows="False",
        log_retention_days=30,
        started_tags="",
        stopped_tags="",
        stack_version="v9.9.9",
        use_aws_organizations="True",
    )


@patch("requests.put")
def test_remote_account_ids_retained(
    mock_requests: MagicMock,
    moto_dynamodb: None,
    app_env: AppEnv,
    config_table: None,
) -> None:
    accounts = ["111111111111", "222222222222"]

    config_table_name = app_env.config_table_name
    org_id = "o-0000000000"
    ddb: DynamoDBClient = boto3.client("dynamodb")
    ddb.put_item(
        TableName=config_table_name,
        Item={
            "type": {"S": "config"},
            "name": {"S": "scheduler"},
            "aws_partition": {"S": "aws"},
            "create_rds_snapshot": {"BOOL": False},
            "default_timezone": {"S": "UTC"},
            "enable_ssm_maintenance_windows": {"BOOL": False},
            "namespace": {"S": "test"},
            "organization_id": {"S": org_id},
            "regions": {"SS": ["us-east-1"]},
            "remote_account_ids": {"SS": accounts},
            "scheduled_services": {"SS": ["ec2"]},
            "scheduler_role_name": {"S": "scheduler-role"},
            "schedule_clusters": {"BOOL": False},
            "schedule_lambda_account": {"BOOL": True},
            "started_tags": {"S": ""},
            "tagname": {"S": "Schedule"},
            "trace": {"BOOL": False},
            "use_metrics": {"BOOL": False},
        },
    )

    event = CustomResourceRequest[ServiceSetupResourceProperties](
        ServiceToken="",
        RequestType="Update",
        ResponseURL="",
        StackId="arn:aws:cloudformation:us-east-1:111111111111:stack/my-stack/00000000-0000-0000-0000-000000000000",
        RequestId="",
        ResourceType="Custom::ServiceSetup",
        LogicalResourceId="",
        PhysicalResourceId="",
        ResourceProperties=resource_properties(org_id, config_table_name),
        OldResourceProperties=resource_properties(org_id, config_table_name),
    )

    SchedulerSetupHandler(event, CustomResourceLambdaContext()).handle_request()

    mock_requests.assert_called_once()
    assert json.loads(mock_requests.call_args.kwargs["data"])["Status"] == "SUCCESS"

    config = ddb.get_item(
        TableName=config_table_name,
        Key={"type": {"S": "config"}, "name": {"S": "scheduler"}},
    )["Item"]

    assert set(config["remote_account_ids"]["SS"]) == set(accounts)
