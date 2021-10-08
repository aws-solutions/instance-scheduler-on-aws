######################################################################################################################
#  Copyright 2021 Amazon.com, Inc. or its affiliates. All Rights Reserved.                                           #
#                                                                                                                    #
#  Licensed under the Apache License Version 2.0 (the "License"). You may not use this file except in compliance     #
#  with the License. A copy of the License is located at                                                             #
#                                                                                                                    #
#      http://www.apache.org/licenses/                                                                               #
#                                                                                                                    #
#  or in the "license" file accompanying this file. This file is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES #
#  OR CONDITIONS OF ANY KIND, express or implied. See the License for the specific language governing permissions    #
#  and limitations under the License.                                                                                #
######################################################################################################################

import pytest
import boto3
from os import environ
from moto import mock_dynamodb2


@pytest.fixture
def aws_credentials():
    """Mocked AWS Credentials for moto"""
    environ['AWS_ACCESS_KEY_ID'] = 'testing'
    environ['AWS_SECRET_ACCESS_KEY'] = 'testing'
    environ['AWS_SECURITY_TOKEN'] = 'testing'
    environ['AWS_SESSION_TOKEN'] = 'testing'



@pytest.fixture
def dynamodb_client(aws_credentials):
    """DDB Mock Client"""
    with mock_dynamodb2():
        connection = boto3.client("dynamodb", region_name="us-west-2")
        yield connection


@pytest.fixture
def dynamodb_client_resource(aws_credentials):
    """DDB Mock Client"""
    with mock_dynamodb2():
        connection = boto3.resource("dynamodb", region_name="us-west-2")
        yield connection
