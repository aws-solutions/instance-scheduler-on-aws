# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from typing import Iterator, TypeVar

T = TypeVar("T")


def paginate(array: list[T], page_size: int) -> Iterator[list[T]]:
    for i in range(0, len(array), page_size):
        yield array[i : i + page_size]
