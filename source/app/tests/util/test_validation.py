# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from typing import Any

import pytest

from instance_scheduler.util.validation import (
    ValidationException,
    require_int,
    require_str,
    validate_boolean,
    validate_int,
    validate_number_item,
    validate_string,
    validate_string_item,
    validate_string_set,
)


def test_require_int_returns_expected() -> None:
    data = {
        "target": 15,
        "fake": 12,
    }
    assert require_int(data, "target") == 15


def test_require_int_raises_error_when_missing() -> None:
    data: dict[str, Any] = {}
    with pytest.raises(ValidationException):
        require_int(data, "target")


def test_require_int_raises_error_when_wrong() -> None:
    data = {"target": "str"}
    with pytest.raises(ValidationException):
        require_int(data, "target")


def test_require_str_returns_expected() -> None:
    data = {
        "target": "t",
        "fake": "f",
    }
    assert require_str(data, "target") == "t"


def test_require_str_raises_error_when_missing() -> None:
    data: dict[str, Any] = {}
    with pytest.raises(ValidationException):
        require_str(data, "target")


def test_require_str_raises_error_when_wrong() -> None:
    data = {"target": 15}
    with pytest.raises(ValidationException):
        require_str(data, "target")


def test_validate_int_passes_when_key_not_set_and_not_required() -> None:
    validate_int({}, "test_val", required=False)


def test_validate_int_fails_when_key_not_set_and_is_required() -> None:
    with pytest.raises(ValidationException):
        validate_int({}, "test_val", required=True)


def test_validate_int_is_required_by_default() -> None:
    # when required is omitted, it defaults to true
    with pytest.raises(ValidationException):
        validate_int({}, "test_val")


def test_validate_int_passes_with_valid_int() -> None:
    validate_int({"test_val": 15}, "test_val")


def test_validate_int_rejects_non_int_values() -> None:
    with pytest.raises(ValidationException):
        validate_int({"test_val": "some_str"}, "test_val")


def test_validate_string_passes_when_key_not_set_and_not_required() -> None:
    validate_string({}, "test_val", required=False)


def test_validate_string_fails_when_key_not_set_and_is_required() -> None:
    with pytest.raises(ValidationException):
        validate_string({}, "test_val", required=True)


def test_validate_string_is_required_by_default() -> None:
    # when required is omitted, it defaults to true
    with pytest.raises(ValidationException):
        validate_string({}, "test_val")


def test_validate_string_passes_with_valid_string() -> None:
    validate_string({"test_val": "str"}, "test_val")


def test_validate_string_rejects_non_string_values() -> None:
    with pytest.raises(ValidationException):
        validate_string({"test_val": 15}, "test_val")


def test_validate_boolean_passes_when_key_not_set_and_not_required() -> None:
    validate_boolean({}, "test_val", required=False)


def test_validate_boolean_fails_when_key_not_set_and_is_required() -> None:
    with pytest.raises(ValidationException):
        validate_boolean({}, "test_val", required=True)


def test_validate_boolean_is_required_by_default() -> None:
    # when required is omitted, it defaults to true
    with pytest.raises(ValidationException):
        validate_boolean({}, "test_val")


def test_validate_boolean_passes_with_valid_boolean() -> None:
    validate_boolean({"test_val": True}, "test_val")


def test_validate_boolean_rejects_non_boolean_values() -> None:
    with pytest.raises(ValidationException):
        validate_boolean(
            {"test_val": "true"}, "test_val"
        )  # string of true is not coerced


def test_validate_string_set_passes_when_key_not_set_and_not_required() -> None:
    validate_string_set({}, "test_val", required=False)


def test_validate_string_set_fails_when_key_not_set_and_is_required() -> None:
    with pytest.raises(ValidationException):
        validate_string_set({}, "test_val", required=True)


def test_validate_string_set_is_required_by_default() -> None:
    # when required is omitted, it defaults to true
    with pytest.raises(ValidationException):
        validate_string_set({}, "test_val")


def test_validate_string_set_passes_with_valid_string_set() -> None:
    validate_string_set({"test_val": {"str", "another_str"}}, "test_val")


def test_validate_string_set_rejects_non_sets() -> None:
    with pytest.raises(ValidationException):
        validate_string_set({"test_val": 15}, "test_val")


def test_validate_string_set_rejects_sets_that_do_not_contain_only_strings() -> None:
    with pytest.raises(ValidationException):
        validate_string_set({"test_val": {"a str", 15}}, "test_val")


def test_validate_string_item_passes_when_key_not_set_and_not_required() -> None:
    assert validate_string_item({}, "key", False)


def test_validate_string_item_fails_when_key_not_set_and_is_required() -> None:
    with pytest.raises(ValidationException):
        validate_string_item({}, "key")


def test_validate_string_item_passes_with_valid_string() -> None:
    assert validate_string_item({"key": {"S": "string"}}, "key")


def test_validate_string_item_rejects_non_string_items() -> None:
    with pytest.raises(ValidationException):
        validate_string_item({"key": {"N": "5"}}, "key")


def test_validate_string_item_rejects_non_string_values() -> None:
    with pytest.raises(ValidationException):
        validate_string_item({"key": {"S": 5}}, "key")


def test_validate_number_item_passes_when_key_not_set_and_not_required() -> None:
    assert validate_number_item({}, "key", False)


def test_validate_number_item_fails_when_key_not_set_and_is_required() -> None:
    with pytest.raises(ValidationException):
        validate_number_item({}, "key")


def test_validate_number_item_passes_with_valid_string() -> None:
    assert validate_number_item({"key": {"N": "10"}}, "key")


def test_validate_number_item_rejects_non_string_items() -> None:
    with pytest.raises(ValidationException):
        validate_number_item({"key": {"S": "my-str"}}, "key")


def test_validate_number_item_rejects_non_string_values() -> None:
    with pytest.raises(ValidationException):
        validate_number_item({"key": {"N": 5}}, "key")
