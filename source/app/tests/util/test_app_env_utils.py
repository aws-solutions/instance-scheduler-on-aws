# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import pytest

from instance_scheduler.util.app_env_utils import env_to_bool, env_to_list


@pytest.mark.parametrize(
    "truthy_value",
    ["True", "true", "true ", "\ttrue\r\n", "\tyes", "Yes", "yes", " yes"],
)
def test_truthy_env_to_bool(truthy_value: str) -> None:
    assert env_to_bool(truthy_value) is True


@pytest.mark.parametrize(
    "falsy_value",
    ["", "False", "false ", "\tfalse\r\n", "No", "no", "\tno", " Anything else"],
)
def test_falsy_env_to_bool(falsy_value: str) -> None:
    assert env_to_bool(falsy_value) is False


@pytest.mark.parametrize(
    "env_val, expected",
    [
        ("", []),
        ("a", ["a"]),
        ("a,b,c", ["a", "b", "c"]),
        ("foo,,bar", ["foo", "bar"]),
        ("foo, bar, ", ["foo", "bar"]),
        ("  ,   foo  , bar, ", ["foo", "bar"]),
    ],
)
def test_to_list(env_val: str, expected: list[str]) -> None:
    assert env_to_list(env_val) == expected
