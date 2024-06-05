# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import pytest

from instance_scheduler.configuration.time_utils import is_valid_time_str


@pytest.mark.parametrize(
    "time_str", ["00:00", "1:00", "01:00", "10:00", "00:05", "00:15", "23:59"]
)
def test_valid_time_str(time_str: str) -> None:
    assert is_valid_time_str(time_str) is True


@pytest.mark.parametrize("time_str", ["abc", "10:5", "1:5", "24:00", "25:00"])
def test_invalid_time_str(time_str: str) -> None:
    assert is_valid_time_str(time_str) is False
