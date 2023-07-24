# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from collections.abc import Iterator

from pytest import fixture


@fixture(autouse=True)
def moto_logs_autouse(moto_logs: None) -> Iterator[None]:
    yield


@fixture(autouse=True)
def mock_log_group_autouse(mock_log_group: None) -> None:
    """noop"""


@fixture(autouse=True)
def moto_sns_autouse(moto_sns: None) -> Iterator[None]:
    yield


@fixture(autouse=True)
def mock_topic_autouse(mock_topic: None) -> None:
    """noop"""
