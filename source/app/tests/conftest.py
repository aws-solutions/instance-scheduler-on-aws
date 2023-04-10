from unittest import mock
import os
import pytest
import boto3
from os import environ
from moto import mock_dynamodb2
import sys


@pytest.fixture
def aws_credentials():
    """Mocked AWS Credentials for moto"""
    environ["AWS_ACCESS_KEY_ID"] = "testing"
    environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    environ["AWS_SECURITY_TOKEN"] = "testing"
    environ["AWS_SESSION_TOKEN"] = "testing"


@pytest.fixture
def dynamodb_client(aws_credentials):
    """DDB Mock Client"""
    with mock_dynamodb2():
        connection = boto3.client("dynamodb", region_name="us-east-1")
        yield connection


@pytest.fixture
def dynamodb_client_resource(aws_credentials):
    """DDB Mock Client"""
    with mock_dynamodb2():
        connection = boto3.resource("dynamodb", region_name="us-east-1")
        yield connection


def mock_version_module():
    module = type(sys)("version")
    module.VERSION = "1.5.0"
    return module


sys.modules["version"] = mock_version_module()
