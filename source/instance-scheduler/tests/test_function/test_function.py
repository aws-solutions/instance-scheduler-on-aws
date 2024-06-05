# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from aws_lambda_powertools.utilities.typing import LambdaContext
else:
    LambdaContext = object


def lambda_handler(_: dict[str, Any], __: LambdaContext) -> None:
    """noop"""


def handle_metrics_uuid_request(_: dict[str, Any], __: LambdaContext) -> None:
    """noop"""


def handle_orchestration_request(_: dict[str, Any], __: LambdaContext) -> None:
    """noop"""


def handle_spoke_registration_event(_: dict[str, Any], __: LambdaContext) -> None:
    """noop"""


def handle_scheduling_request(_: dict[str, Any], __: LambdaContext) -> None:
    """noop"""
