# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from instance_scheduler.model.period_identifier import PeriodIdentifier


def test_simple_identifier() -> None:
    pid = PeriodIdentifier.of("period_name")
    assert pid == "period_name"
    assert pid.name == "period_name"


def test_identifier_with_type() -> None:
    pid = PeriodIdentifier.of("period_name", "desired_type")
    assert pid == "period_name@desired_type"
    assert pid.name == "period_name"
    assert pid.desired_type == "desired_type"
