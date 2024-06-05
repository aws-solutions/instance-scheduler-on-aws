# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from dataclasses import replace
from os import environ
from typing import Optional
from unittest.mock import patch

from pytest import fixture, raises

import instance_scheduler.util.app_env
from instance_scheduler.util.app_env import (
    AppEnv,
    AppEnvError,
    env_to_bool,
    env_to_list,
    get_app_env,
)
from tests.test_utils.app_env_utils import env_from_app_env, example_app_env


@fixture(autouse=True)
def reset_cached_env() -> None:
    instance_scheduler.util.app_env._app_env = None


def test_to_bool() -> None:
    assert env_to_bool("True")
    assert env_to_bool("true")
    assert env_to_bool("true ")
    assert env_to_bool("Yes")
    assert env_to_bool("yes")
    assert env_to_bool(" yes")

    assert not env_to_bool("")
    assert not env_to_bool("False")
    assert not env_to_bool("false")
    assert not env_to_bool("\tfalse\r\n")
    assert not env_to_bool("No")
    assert not env_to_bool("no")
    assert not env_to_bool("\tno")
    assert not env_to_bool("Anything else")


def test_to_list() -> None:
    assert env_to_list("") == []

    assert env_to_list("a") == ["a"]
    assert env_to_list("a,b,c") == ["a", "b", "c"]

    assert env_to_list("foo,,bar") == ["foo", "bar"]
    assert env_to_list("foo, bar, ") == ["foo", "bar"]
    assert env_to_list("  ,   foo  , bar, ") == ["foo", "bar"]


def test_get_app_env() -> None:
    expected_env = example_app_env()

    app_env: Optional[AppEnv] = None
    with patch.dict(environ, env_from_app_env(expected_env), clear=True):
        app_env = get_app_env()
        assert get_app_env() is app_env

    assert app_env == expected_env


def test_missing_key() -> None:
    expected_env = example_app_env()
    my_env = env_from_app_env(expected_env)

    missing_key = "SCHEDULER_FREQUENCY"
    del my_env[missing_key]

    with patch.dict(environ, my_env, clear=True), raises(AppEnvError) as err:
        get_app_env()

    assert (
        str(err.value)
        == f"Missing required application environment variable: {missing_key}"
    )


def test_invalid_timezone() -> None:
    expected_env = example_app_env()
    my_env = env_from_app_env(expected_env)

    invalid_timezone = "something_invalid"
    my_env["DEFAULT_TIMEZONE"] = invalid_timezone

    with patch.dict(environ, my_env, clear=True), raises(AppEnvError) as err:
        get_app_env()

    assert (
        str(err.value)
        == f"Invalid timezone: No time zone found with key {invalid_timezone}"
    )


def test_scheduled_services() -> None:
    app_env = example_app_env()

    app_env_ec2_enabled = replace(
        app_env,
        enable_ec2_service=True,
        enable_rds_service=False,
        enable_neptune_service=False,
        enable_docdb_service=False,
    )
    assert set(app_env_ec2_enabled.scheduled_services()) == {"ec2"}

    app_env_rds_enabled = replace(
        app_env,
        enable_ec2_service=False,
        enable_rds_service=True,
        enable_neptune_service=False,
        enable_docdb_service=False,
    )
    assert set(app_env_rds_enabled.scheduled_services()) == {"rds"}

    app_env_both_enabled = replace(
        app_env,
        enable_ec2_service=True,
        enable_rds_service=True,
        enable_neptune_service=False,
        enable_docdb_service=False,
    )
    assert set(app_env_both_enabled.scheduled_services()) == {"ec2", "rds"}

    app_env_neptune_enabled = replace(
        app_env,
        enable_neptune_service=True,
        enable_rds_service=False,
        enable_ec2_service=False,
        enable_docdb_service=False,
    )
    assert set(app_env_neptune_enabled.scheduled_services()) == {"rds"}

    app_env_docdb_enabled = replace(
        app_env,
        enable_docdb_service=True,
        enable_rds_service=False,
        enable_ec2_service=False,
        enable_neptune_service=False,
    )
    assert set(app_env_docdb_enabled.scheduled_services()) == {"rds"}
