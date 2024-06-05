# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from collections.abc import Mapping
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Optional,
    Sequence,
    TypedDict,
    TypeGuard,
    TypeVar,
)

if TYPE_CHECKING:
    from mypy_boto3_dynamodb.type_defs import AttributeValueTypeDef
else:
    AttributeValueTypeDef = object

OptionalAttributeValue = TypedDict(
    "OptionalAttributeValue",
    {
        "S": Optional[str],
        "N": Optional[str],
        "B": Optional[bytes],
        "SS": Optional[Sequence[str]],
        "NS": Optional[Sequence[str]],
        "BS": Optional[Sequence[bytes]],
        "M": Optional[Mapping[str, Any]],
        "L": Optional[Sequence[Any]],
        "NULL": Optional[bool],
        "BOOL": Optional[bool],
    },
    total=False,
)

ParseFunctionReturnType = TypeVar("ParseFunctionReturnType")
ParseFunctionInputType = TypeVar("ParseFunctionInputType")
DefaultType = TypeVar("DefaultType")


def optionally(
    parsing_func: Callable[[ParseFunctionInputType], ParseFunctionReturnType],
    input_to_parse: Optional[ParseFunctionInputType],
    default: DefaultType,
) -> ParseFunctionReturnType | DefaultType:
    """
    parse an Optional[T] input using any other parsing function that accepts T (not optional)

    if the provided input is falsy, then default will be returned. Otherwise the parsing function will be invoked to
    parse the input
    """
    if input_to_parse:
        return parsing_func(input_to_parse)
    else:
        return default


def parse_str(value: AttributeValueTypeDef) -> str:
    """
    parse an AttributeValueTypeDef as a str value

    Will throw an error if values is not of type S
    """
    if "S" in value:
        return value["S"]
    else:
        raise ValueError(f"unable to parse string {value}, must be of type 'S'")


def parse_bool(value: AttributeValueTypeDef) -> bool:
    """
    coerce an AttributeValueTypeDef returned from a DynamoDB item into a boolean value

    Support values that will be coerced into booleans:

    - S types containing "true" or "false" (case-insensitive)
    - BOOL types of True/False
    """
    if "S" in value:
        if value["S"].lower() == "true":
            return True
        elif value["S"].lower() == "false":
            return False
        else:
            raise ValueError(f"unknown bool value {value}, must be 'true' or 'false'")
    elif "BOOL" in value:
        return value["BOOL"]
    else:
        raise ValueError(
            f"unable to parse bool value from {value}, must be of type 'S' or 'BOOL'"
        )


def parse_str_set(value: AttributeValueTypeDef) -> set[str]:
    """
    coerce an AttributeValueTypeDef returned from a DynamoDB item into a String sequences

    Support values that will be coerced into String sequences:

    - SS types containing lists of strings
    - S types containing comma-separated lists values (spaces are not stripped!)
    """
    if "S" in value:
        return set(value["S"].split(",") if value["S"] != "" else [])
    elif "SS" in value:
        return set(value["SS"])
    else:
        raise ValueError(
            f"unable to parse string set from {value}, must be of type 'S' or 'SS'"
        )


def skip_if_none(
    key: str, value: OptionalAttributeValue
) -> dict[str, AttributeValueTypeDef]:
    """
    helper function for skipping inclusion into a ddb item if the element does not have a configured value. This allows
    saving optional values to dynamodb that should not be included in the item if they are not configured
    example usage:

    {
        **skip_if_none("description", {"S": string_that_might_be_empty)
    }

    differs from skip_if_empty() -- empty sequences will be included while None sequences will be excluded
    """
    if _is_non_none_entry(value):
        return {key: value}
    else:
        return {}


def skip_if_empty(
    key: str, value: OptionalAttributeValue
) -> dict[str, AttributeValueTypeDef]:
    """
    helper function for skipping inclusion into a ddb item if the element does not have a configured value. This allows
    saving optional values to dynamodb that should not be included in the item if they are not configured
    example usage:

    {
        **skip_if_empty("periods", {"SS": sequence_that_might_be_empty)
    }

    differs from skip_if_none() -- empty sequences will be excluded the same as if they were set to None
    """
    if _is_non_empty_entry(value):
        return {key: value}
    else:
        return {}


def _is_non_none_entry(
    entry: OptionalAttributeValue,
) -> TypeGuard[AttributeValueTypeDef]:
    return any(value is not None for value in entry.values())


def _is_non_empty_entry(
    entry: OptionalAttributeValue,
) -> TypeGuard[AttributeValueTypeDef]:
    for val in entry.values():
        if val is not None:
            # sequences/maps need the extra len check to confirm non-empty
            if isinstance(val, Sequence) or isinstance(val, Mapping):
                if len(val) > 0:
                    return True
            else:
                return True
    return False
