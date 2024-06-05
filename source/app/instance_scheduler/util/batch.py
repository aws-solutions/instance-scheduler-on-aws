# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Final, Generic, Self, TypeVar

T = TypeVar("T")


@dataclass
class FailureResponse(Generic[T]):
    failed_input: T
    error: Exception


U = TypeVar("U")


@dataclass
class BisectRetryResponse(Generic[T, U]):
    success_responses: list[U] = field(default_factory=list)
    intermediate_responses: list[FailureResponse[list[T]]] = field(default_factory=list)
    failure_responses: list[FailureResponse[T]] = field(default_factory=list)

    def merge(self, *others: "BisectRetryResponse[T, U]") -> Self:
        for other in others:
            self.success_responses.extend(other.success_responses)
            self.intermediate_responses.extend(other.intermediate_responses)
            self.failure_responses.extend(other.failure_responses)
        return self


def bisect_retry(
    inputs: list[T], action: Callable[[list[T]], U]
) -> BisectRetryResponse[T, U]:
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
    length: Final = len(inputs)
    if length == 0:
        return BisectRetryResponse()
    try:
        return BisectRetryResponse(success_responses=[action(inputs)])
    except Exception as err:
        if length == 1:
            return BisectRetryResponse(
                failure_responses=[FailureResponse(failed_input=inputs[0], error=err)]
            )
        else:
            result: BisectRetryResponse[T, U] = BisectRetryResponse(
                intermediate_responses=[FailureResponse(failed_input=inputs, error=err)]
            )

        midpoint: Final = length // 2
        left: Final = bisect_retry(inputs[0:midpoint], action)
        right: Final = bisect_retry(inputs[midpoint:], action)
        return result.merge(left, right)
