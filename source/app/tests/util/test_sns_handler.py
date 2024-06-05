# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from collections.abc import Iterator
from logging import Logger
from typing import TYPE_CHECKING, Any, Final

import boto3
from botocore.exceptions import ClientError
from moto.core.models import DEFAULT_ACCOUNT_ID
from moto.sns.models import SNSBackend, sns_backends
from pytest import fixture, raises

from instance_scheduler.util.sns_handler import SnsHandler

if TYPE_CHECKING:
    from mypy_boto3_sns.client import SNSClient
else:
    SNSClient = object


@fixture
def mock_topic(moto_backend: None) -> Iterator[str]:
    sns: Final[SNSClient] = boto3.client("sns")
    response: Final = sns.create_topic(Name="my_topic")
    yield response["TopicArn"]


log_group_name: Final = "log_group"
log_stream_name: Final = "log_stream"


@fixture
def logger_with_handler(mock_topic: str) -> Iterator[Logger]:
    logger: Final = Logger(__name__)
    handler: Final = SnsHandler(
        topic_arn=mock_topic,
        log_group_name=log_group_name,
        log_stream_name=log_stream_name,
    )
    logger.addHandler(handler)

    yield logger


def get_sent_notifications(
    topic_arn: str,
) -> list[tuple[str, str, str | None, dict[str, Any] | None, str | None]]:
    sns_backend: Final[SNSBackend] = sns_backends[DEFAULT_ACCOUNT_ID]["us-east-1"]
    return sns_backend.topics[topic_arn].sent_notifications


def test_sns_handler_publishes_warning(
    logger_with_handler: Logger, mock_topic: str
) -> None:
    message: Final = "warning"
    logger_with_handler.warning(message)

    sent_notifications: Final = get_sent_notifications(mock_topic)
    assert len(sent_notifications) == 1
    assert (
        sent_notifications[0][1]
        == f"Loggroup: {log_group_name}\nLogstream {log_stream_name}\nWARNING : {message}"
    )


def test_sns_handler_publishes_error(
    logger_with_handler: Logger, mock_topic: str
) -> None:
    message: Final = "error"
    logger_with_handler.error(message)

    sent_notifications: Final = get_sent_notifications(mock_topic)
    assert len(sent_notifications) == 1
    assert (
        sent_notifications[0][1]
        == f"Loggroup: {log_group_name}\nLogstream {log_stream_name}\nERROR : {message}"
    )


def test_sns_handler_suppresses_info(
    logger_with_handler: Logger, mock_topic: str
) -> None:
    message: Final = "info"
    logger_with_handler.info(message)

    sent_notifications: Final = get_sent_notifications(mock_topic)
    assert len(sent_notifications) == 0


def test_sns_handler_raises_exception_when_raise_exceptions_flag_is_true(
    moto_backend: None,
) -> None:
    logger: Final = Logger(__name__)
    handler: Final = SnsHandler(
        topic_arn="arn:aws:sns:us-east-1:111111111111:fake_topic",
        log_group_name=log_group_name,
        log_stream_name=log_stream_name,
        raise_exceptions=True,
    )
    logger.addHandler(handler)

    with raises(ClientError):
        logger.warning("warning")


def test_sns_handler_swallows_exception_when_raise_exceptions_flag_is_false(
    moto_backend: None,
) -> None:
    logger: Final = Logger(__name__)
    handler: Final = SnsHandler(
        topic_arn="arn:aws:sns:us-east-1:111111111111:fake_topic",
        log_group_name=log_group_name,
        log_stream_name=log_stream_name,
        raise_exceptions=False,
    )
    logger.addHandler(handler)

    logger.warning("warning")  # Does not throw exception
