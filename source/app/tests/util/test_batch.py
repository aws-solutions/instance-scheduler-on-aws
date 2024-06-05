# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import operator
from collections.abc import Callable
from functools import reduce
from typing import Final, TypeVar
from unittest.mock import MagicMock, call

from instance_scheduler.util.batch import bisect_retry

T = TypeVar("T")


def create_action_failing_on_inputs(
    failing_inputs: frozenset[T],
) -> Callable[[list[T]], None]:
    def action_failing_on_inputs(inputs: list[T]) -> None:
        for item in inputs:
            if item in failing_inputs:
                raise ValueError(item)

    return action_failing_on_inputs


action_not_failing: Final = MagicMock(
    side_effect=create_action_failing_on_inputs(frozenset())
)


def test_bisect_retry_no_inputs_not_called() -> None:
    bisect_retry([], action_not_failing)
    action_not_failing.assert_not_called()


def test_bisect_retry_no_errors_called_once() -> None:
    inputs: Final = [[0], list(range(2)), list(range(1000))]
    for example in inputs:
        action_not_failing.reset_mock()
        bisect_retry(example, action_not_failing)
        action_not_failing.assert_called_once_with(example)


def test_bisect_retry_single_error() -> None:
    failing_input: Final = 2
    action_fail_single: Final = MagicMock(
        side_effect=create_action_failing_on_inputs(frozenset([failing_input]))
    )

    # single failing input called once, failure response
    result = bisect_retry([failing_input], action_fail_single)
    assert len(result.success_responses) == 0
    assert len(result.intermediate_responses) == 0
    assert len(result.failure_responses) == 1
    assert result.failure_responses[0].failed_input == failing_input
    assert isinstance(result.failure_responses[0].error, ValueError)
    action_fail_single.assert_called_once_with([failing_input])
    action_fail_single.reset_mock()

    # one bad input out of three, should split
    result = bisect_retry([2, 3, 4], action_fail_single)
    assert len(result.success_responses) == 1
    assert len(result.intermediate_responses) == 1
    assert len(result.failure_responses) == 1
    assert result.failure_responses[0].failed_input == failing_input
    assert isinstance(result.failure_responses[0].error, ValueError)
    assert action_fail_single.call_count == 3
    action_fail_single.assert_has_calls([call([2, 3, 4]), call([2]), call([3, 4])])
    action_fail_single.reset_mock()

    # one bad input out of ten, should split multiple times
    result = bisect_retry(list(range(10)), action_fail_single)
    assert len(result.success_responses) == 3
    assert len(result.intermediate_responses) == 3
    assert len(result.failure_responses) == 1
    assert result.failure_responses[0].failed_input == failing_input
    assert isinstance(result.failure_responses[0].error, ValueError)
    assert action_fail_single.call_count == 7
    action_fail_single.assert_has_calls(
        [
            call([0, 1, 2, 3, 4, 5, 6, 7, 8, 9]),
            call([0, 1, 2, 3, 4]),
            call([0, 1]),
            call([2, 3, 4]),
            call([2]),
            call([3, 4]),
            call([5, 6, 7, 8, 9]),
        ]
    )


def test_bisect_retry_many_errors() -> None:
    input_size: Final = 10000
    failing_inputs: Final = range(0, input_size, 2)
    action_fail_even: Final = MagicMock(
        side_effect=create_action_failing_on_inputs(frozenset(failing_inputs))
    )

    inputs: Final = list(range(input_size))
    result = bisect_retry(inputs, action_fail_even)

    # half failure responses, half success responses (None)
    assert len(result.success_responses) == int(input_size / 2)
    assert len(result.intermediate_responses) == input_size - 1
    assert len(result.failure_responses) == int(input_size / 2)
    # expected sum if all failing inputs are represented in failure responses
    expected_sum: Final = reduce(operator.add, failing_inputs)
    actual_sum = 0
    for item in result.failure_responses:
        actual_sum += item.failed_input
        assert isinstance(item.error, ValueError)
    for item in result.success_responses:
        assert item is None
    assert actual_sum == expected_sum

    # \sum_{i=0}^{log_2(n)} 2^i = 2n-1
    assert action_fail_even.call_count == 2 * input_size - 1
