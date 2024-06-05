# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from typing import Optional

import pytest
from mypy_boto3_dynamodb.type_defs import AttributeValueTypeDef

from instance_scheduler.model.ddb_item_utils import (
    OptionalAttributeValue,
    optionally,
    parse_bool,
    parse_str_set,
    skip_if_empty,
    skip_if_none,
)


def test_optional_attribute_value_type_matches_boto_type() -> None:
    # ensures no drift between the actual type-def and the extension used by ddb_item_utils
    assert all(
        key in AttributeValueTypeDef.__annotations__.keys()
        for key in OptionalAttributeValue.__annotations__.keys()
    )
    assert all(
        key in OptionalAttributeValue.__annotations__.keys()
        for key in AttributeValueTypeDef.__annotations__.keys()
    )


@pytest.mark.parametrize(
    "input,expected_out",
    [
        (None, None),
        ({"S": "True"}, True),
        ({"S": "FALSE"}, False),
        ({"BOOL": True}, True),
        ({"BOOL": False}, False),
    ],
)
def test_parse_bool_optionally(
    input: AttributeValueTypeDef, expected_out: Optional[bool]
) -> None:
    assert optionally(parse_bool, input, default=None) == expected_out


@pytest.mark.parametrize(
    "input,expected_out",
    [
        ({"S": "True"}, True),
        ({"S": "FALSE"}, False),
        ({"BOOL": True}, True),
        ({"BOOL": False}, False),
    ],
)
def test_parse_bool(input: AttributeValueTypeDef, expected_out: Optional[bool]) -> None:
    assert parse_bool(input) == expected_out


@pytest.mark.parametrize(
    "invalid_input",
    [
        {"S": "Yes"},
        {"S": "anything else"},
        {"SS": ["true"]},  # wrong type (SS not S)
        {"S": ""},
        {"N": "12"},
    ],
)
def test_parse_bool_throws_error_on_invalid_input(
    invalid_input: AttributeValueTypeDef,
) -> None:
    with pytest.raises(ValueError):
        parse_bool(invalid_input)


@pytest.mark.parametrize(
    "input,expected_out",
    [
        ({"S": "a,b,c"}, {"a", "b", "c"}),
        ({"S": "FALSE"}, {"FALSE"}),
        ({"S": ""}, set()),
        ({"S": " "}, {" "}),
        (
            {"S": "a big string,another big string"},
            {"a big string", "another big string"},
        ),
        ({"SS": []}, set()),
        ({"SS": ["a", "b", "c"]}, {"a", "b", "c"}),
    ],
)
def test_parse_str_set(input: AttributeValueTypeDef, expected_out: set[str]) -> None:
    assert parse_str_set(input) == expected_out


@pytest.mark.parametrize(
    "invalid_input",
    [{"N": "12"}, {"Bool": True}, {"NS": ["12", "13", "23"]}],
)
def test_parse_str_set_throws_error_on_invalid_input(
    invalid_input: AttributeValueTypeDef,
) -> None:
    with pytest.raises(ValueError):
        parse_str_set(invalid_input)


@pytest.mark.parametrize(
    "valid_input",
    [
        {"S": "a_str"},
        {"N": "str"},
        {"B": 8},
        {"SS": ["a", "str"]},
        {"SS": []},
        {"NS": ["str"]},
        {"NS": []},
        {"BS": [5, 5]},
        {"BS": []},
        {"M": {"some": "mapping"}},
        {"L": ["any", "sequence"]},
        {"NULL": True},
        {"BOOL": False},
    ],
)
def test_skip_if_none_does_not_skip_valid_inputs(
    valid_input: OptionalAttributeValue,
) -> None:
    assert skip_if_none("test", valid_input) == {"test": valid_input}


@pytest.mark.parametrize(
    "none_input",
    [
        {"S": None},
        {"N": None},
        {"B": None},
        {"SS": None},
        {"NS": None},
        {"BS": None},
        {"M": None},
        {"L": None},
        {"NULL": None},
        {"BOOL": None},
    ],
)
def test_skip_if_none_skips_none_inputs(none_input: OptionalAttributeValue) -> None:
    assert skip_if_none("test", none_input) == {}


@pytest.mark.parametrize(
    "valid_input",
    [
        {"S": "a_str"},
        {"N": "str"},
        {"B": 8},
        {"SS": ["a", "str"]},
        {"SS": ["str"]},
        {"NS": ["str"]},
        {"BS": [5, 5]},
        {"M": {"some": "mapping"}},
        {"L": ["any", "sequence"]},
        {"NULL": True},
        {"BOOL": False},
    ],
)
def test_skip_if_empty_does_not_skip_valid_inputs(
    valid_input: OptionalAttributeValue,
) -> None:
    assert skip_if_empty("test", valid_input) == {"test": valid_input}


@pytest.mark.parametrize(
    "empty_input",
    [
        {"S": None},
        {"N": None},
        {"B": None},
        {"SS": None},
        {"NS": None},
        {"BS": None},
        {"M": None},
        {"L": None},
        {"NULL": None},
        {"BOOL": None},
        {"SS": []},
        {"NS": []},
        {"BS": []},
        {"M": {}},
        {"L": []},
    ],
)
def test_skip_if_empty_skips_empty_inputs(empty_input: OptionalAttributeValue) -> None:
    assert skip_if_empty("test", empty_input) == {}
