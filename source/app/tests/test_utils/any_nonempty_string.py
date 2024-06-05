# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from typing import Any

import pytest


class AnyNonEmptyString(str):
    """helper object for asserting equals against any non-empty string value"""

    def __str__(self) -> str:
        return "##AnyNonEmptyString##"

    def __len__(self) -> int:
        return self.__str__().__len__()

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, str):
            return False
        return bool(other.strip())

    def __ne__(self, other: Any) -> bool:
        return not self.__eq__(other)


@pytest.mark.parametrize("valid_input", ["string", "false", "-1"])
def test_equals_non_empty_string(valid_input: str) -> None:
    assert valid_input == AnyNonEmptyString()
    assert AnyNonEmptyString() == valid_input


@pytest.mark.parametrize("invalid_input", ["", " ", None])
def test_not_equals_empty_string(invalid_input: str) -> None:
    assert invalid_input != AnyNonEmptyString()
    assert AnyNonEmptyString() != invalid_input
