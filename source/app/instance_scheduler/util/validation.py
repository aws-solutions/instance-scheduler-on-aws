# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from typing import Any, Callable, Mapping, TypeGuard, cast


class ValidationException(Exception):
    pass


def require_int(untyped_dict: Mapping[str, Any], key: str) -> int:
    validate_int(untyped_dict, key, True)
    return cast(int, untyped_dict[key])


def require_str(untyped_dict: Mapping[str, Any], key: str) -> str:
    validate_string(untyped_dict, key, True)
    return cast(str, untyped_dict[key])


def validate_int(  # NOSONAR -- (duplicate-returns) function is expected to return true or throw an error per the TypeGuard spec
    untyped_dict: Mapping[str, Any], key: str, required: bool = True
) -> TypeGuard[Mapping[str, Any]]:
    """
    :param untyped_dict: a mapping of strings to unknown values
    :param key: the key to check
    :param required: if true, an error will be thrown if the value is missing, if false, no error will be thrown
    :return: true if the value stored at {key} is a str. a ValidationException will be raised otherwise
    """
    value = untyped_dict.get(key, None)
    if value is None:
        if required:
            raise ValidationException(f"required key {key} is missing")
        else:
            return True
    if type(value) is not int:
        raise ValidationException(f"{key} must be an int, found {type(value)}")
    return True


def validate_string(  # NOSONAR -- (duplicate-returns) function is expected to return true or throw an error per the TypeGuard spec
    untyped_dict: Mapping[str, Any], key: str, required: bool = True
) -> TypeGuard[Mapping[str, Any]]:
    """
    :param untyped_dict: a mapping of strings to unknown values
    :param key: the key to check
    :param required: if true, an error will be thrown if the value is missing, if false, no error will be thrown
    :return: true if the value stored at {key} is a str. a ValidationException will be raised otherwise
    """
    value = untyped_dict.get(key, None)
    if value is None:
        if required:
            raise ValidationException(f"required key {key} is missing")
        else:
            return True
    if type(value) is not str:
        raise ValidationException(f"{key} must be a string, found {type(value)}")
    return True


def validate_string_list(  # NOSONAR -- (duplicate-returns) function is expected to return true or throw an error per the TypeGuard spec
    untyped_dict: Mapping[str, Any], key: str, required: bool = True
) -> TypeGuard[Mapping[str, Any]]:
    """
    :param untyped_dict: a mapping of strings to unknown values
    :param key: the key to check
    :param required: if true, an error will be thrown if the value is missing, if false, no error will be thrown
    :return: true if the value stored at {key} is a list[str]. a ValidationException will be raised otherwise
    """
    value = untyped_dict.get(key, None)
    if value is None:
        if required:
            raise ValidationException(f"required key {key} is missing")
        else:
            return True
    if type(value) is not list:
        raise ValidationException(f"{key} must be a list, found {type(value)}")
    for item in value:
        if type(item) is not str:
            raise ValidationException(
                f"All elements of {key} must be strings, found {type(item)}"
            )
    return True


def validate_boolean(  # NOSONAR -- (duplicate-returns) function is expected to return true or throw an error per the TypeGuard spec
    untyped_dict: Mapping[str, Any], key: str, required: bool = True
) -> TypeGuard[Mapping[str, Any]]:
    """
    :param untyped_dict: a mapping of strings to unknown values
    :param key: the key to check
    :param required: if true, an error will be thrown if the value is missing, if false, no error will be thrown
    :return: true if the value stored at {key} is a bool. a ValidationException will be raised otherwise
    """
    value = untyped_dict.get(key, None)
    if value is None:
        if required:
            raise ValidationException(f"required key {key} is missing")
        else:
            return True
    if type(value) is not bool:
        raise ValidationException(f"{key} must be a boolean, found {type(value)}")
    return True


def validate_string_set(  # NOSONAR -- (duplicate-returns) function is expected to return true or throw an error per the TypeGuard spec
    untyped_dict: Mapping[str, Any], key: str, required: bool = True
) -> TypeGuard[Mapping[str, Any]]:
    """
    :param untyped_dict: a mapping of strings to unknown values
    :param key: the key to check
    :param required: if true, an error will be thrown if the value is missing, if false, no error will be thrown
    :return: true if the value stored at {key} is a set[str]. a ValidationException will be raised otherwise
    """
    value = untyped_dict.get(key, None)
    if value is None:
        if required:
            raise ValidationException(f"required key {key} is missing")
        else:
            return True
    if type(value) is not set:
        raise ValidationException(f"{key} must be a set, found {type(value)}")
    for element in value:
        if type(element) is not str:
            raise ValidationException(
                f"all elements in {key} must be strings, found {element} which is {type(value)}"
            )
    return True


def validate_sub_dict(
    untyped_dict: Mapping[str, Any],
    key: str,
    validator: Callable[[Mapping[str, Any]], bool],
    required: bool = True,
) -> TypeGuard[Mapping[str, Any]]:
    """
    validate the shape of a dictionary (the sub-dict) within another dictionary
    :param untyped_dict: a mapping of strings to unknown values
    :param key: the key to check
    :param required: if true, an error will be thrown if the value is missing, if false, no error will be thrown
    :param validator: sub validator that will be called to validate the sub_dict
    :return: true if the value stored at {key} is a str. a ValidationException will be raised otherwise
    """
    value = untyped_dict.get(key, None)
    if value is None:
        if required:
            raise ValidationException(f"required key {key} is missing")
        else:
            return True
    if type(value) is not dict:
        raise ValidationException(f"{key} must be a dict, found {type(value)}")
    try:
        return validator(value)
    except ValidationException as ve:
        raise ValidationException(f"{key} failed validation: {ve}")


def validate_string_item(  # NOSONAR -- (duplicate-returns) function is expected to return true or throw an error per the TypeGuard spec
    untyped_dict: Mapping[str, Any], key: str, required: bool = True
) -> TypeGuard[Mapping[str, Any]]:
    """
    :param untyped_dict: a mapping of strings to unknown values
    :param key: the key to check
    :param required: if true, an error will be thrown if the value is missing, if false, no error will be thrown
    :return: true if the value stored at {key} is a set[str]. a ValidationException will be raised otherwise
    """
    value = untyped_dict.get(key, None)
    if value is None:
        if required:
            raise ValidationException(f"required key {key} is missing")
        else:
            return True
    if type(value) is not dict:
        raise ValidationException(f"{key} must be a dict, found {type(value)}")
    if "S" not in value:
        raise ValidationException(f'{key} must have attribute "S", found {value}')
    if type(value["S"]) is not str:
        raise ValidationException(
            f'{key}["S"] must be a string, found {type(value["S"])}'
        )
    return True


def validate_number_item(  # NOSONAR -- (duplicate-returns) function is expected to return true or throw an error per the TypeGuard spec
    untyped_dict: Mapping[str, Any], key: str, required: bool = True
) -> TypeGuard[Mapping[str, Any]]:
    """
    :param untyped_dict: a mapping of strings to unknown values
    :param key: the key to check
    :param required: if true, an error will be thrown if the value is missing, if false, no error will be thrown
    :return: true if the value stored at {key} is a set[str]. a ValidationException will be raised otherwise
    """
    value = untyped_dict.get(key, None)
    if value is None:
        if required:
            raise ValidationException(f"required key {key} is missing")
        else:
            return True
    if type(value) is not dict:
        raise ValidationException(f"{key} must be a dict, found {type(value)}")
    if "N" not in value:
        raise ValidationException(f'{key} must have attribute "N", found {value}')
    if type(value["N"]) is not str:
        raise ValidationException(
            f'{key}["N"] must be a string, found {type(value["N"])}'
        )
    return True
