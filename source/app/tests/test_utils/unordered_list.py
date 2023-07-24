# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from typing import Any, TypeVar

T = TypeVar("T")


class UnorderedList(list[T]):
    """helper object for asserting unordered equals on lists"""

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, list):
            return False

        if len(self) != len(other):
            return False

        temp = other.copy()
        for item in self:
            try:
                temp.remove(item)
            except ValueError:
                return False

        return True

    def __ne__(self, other: Any) -> bool:
        return not self.__eq__(other)


def test_matches_normally() -> None:
    assert UnorderedList([1, 2, 3]) == UnorderedList([3, 2, 1])


def test_not_fooled_by_duplicates() -> None:
    assert UnorderedList([1, 2, 2]) != UnorderedList([3, 2, 1])
