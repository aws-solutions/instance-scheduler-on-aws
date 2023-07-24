# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from aws_lambda_powertools.utilities.typing import LambdaContext

from instance_scheduler.handler.spoke_registration import SpokeRegistrationHandler
from instance_scheduler.util.app_env import AppEnv
from instance_scheduler.util.dynamodb_utils import DynamoDBUtils


def test_handler(app_env: AppEnv, config_table: None) -> None:
    create_event = {
        "version": "0",
        "id": "c4556ddf-88ad-1b22-e482-19f2d72eb7e3",
        "detail-type": "Parameter Store Change",
        "source": "aws.ssm",
        "account": "111111111111",
        "time": "2021-08-19T06:26:38Z",
        "region": "us-east-1",
        "resources": [
            "arn:aws:ssm:us-east-1:111111111111:parameter/scheduler/do-not-delete-manually/static"
        ],
        "detail": {
            "name": "/scheduler/do-not-delete-manually/static",
            "type": "String",
            "operation": "Create",
        },
    }
    dynamodb_table = DynamoDBUtils.get_dynamodb_table_resource_ref(
        app_env.config_table_name
    )
    dynamodb_table.put_item(
        Item={"type": "config", "name": "scheduler", "namespace": "static"}
    )
    handler = SpokeRegistrationHandler(create_event, LambdaContext())
    response: bool | str = handler.is_handling_request(create_event)
    assert response is True

    response = handler.handle_request()
    assert response == "Exiting event bus request handler"
    delete_event = {
        "version": "0",
        "id": "c4556ddf-88ad-1b22-e482-19f2d72eb7e3",
        "detail-type": "Parameter Store Change",
        "source": "aws.ssm",
        "account": "111111111111",
        "time": "2021-08-19T06:26:38Z",
        "region": "us-east-1",
        "resources": [
            "arn:aws:ssm:us-east-1:111111111111:parameter/scheduler/do-not-delete-manually/static"
        ],
        "detail": {
            "name": "/scheduler/do-not-delete-manually/static",
            "type": "String",
            "operation": "Delete",
        },
    }
    handler = SpokeRegistrationHandler(delete_event, LambdaContext())
    response = handler.is_handling_request(delete_event)
    assert response is True

    response = handler.handle_request()
    assert response == "Exiting event bus request handler"
