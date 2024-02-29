# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from pytest import fixture


@fixture(autouse=True)
def auto_setup_log_group(mock_log_group: None) -> None:
    """noop"""


@fixture(autouse=True)
def auto_setup_sns_error_reporting_topic(mock_sns_errors_topic: None) -> None:
    """noop"""
