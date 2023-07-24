# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final, Generic, TypeVar

T = TypeVar("T")


@dataclass
class FailureResponse(Generic[T]):
    failed_input: T
    error: Exception


U = TypeVar("U")


def bisect_retry(
    inputs: list[T], action: Callable[[list[T]], U]
) -> list[U | FailureResponse[T]]:
    """
    Retry an action taking a list of inputs by successively splitting the inputs in half

    When performing operations on a list of inputs that can fail due to any one of the
    inputs being invalid, but with no way to know which input(s) caused the failure,
    retry the operation on successively smaller inputs until it succeeds.

    This function should minimize the number of actions taken when no inputs are
    problematic, and it should minimize the number of calls needed for non-problematic
    inputs to succeed.

    Assume that actions with empty lists would be no-ops and skip them.

    Assume that if the operation fails on a list of size one, that input is problematic
    and will never result in a successful action. For this reason, `action` should
    handle ephemeral errors.

    Return a list of responses from successful actions. For actions that failed, return
    a tuple of the single input item that resulted in an error and the error that was
    raised.
    """
    if not inputs:
        return []
    try:
        return [action(inputs)]
    except Exception as err:
        length: Final = len(inputs)
        if length == 1:
            return [FailureResponse(failed_input=inputs[0], error=err)]

    midpoint: Final = length // 2
    left: Final = bisect_retry(inputs[0:midpoint], action)
    right: Final = bisect_retry(inputs[midpoint:], action)
    return left + right
