# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import pytest
from _pytest.fixtures import fixture

from instance_scheduler.handler.spoke_registration import (
    SpokeRegistrationEnvironment,
    SpokeRegistrationHandler,
    SpokeRequest,
    validate_spoke_request,
)
from instance_scheduler.model.store.ddb_config_item_store import DdbConfigItemStore
from instance_scheduler.util.validation import ValidationException
from tests.logger import MockLogger


def registration_request(account_id: str) -> SpokeRequest:
    return {
        "account": account_id,
        "operation": "Register",
    }


def deregistration_request(account_id: str) -> SpokeRequest:
    return {
        "account": account_id,
        "operation": "Deregister",
    }


@fixture
def spoke_registration_env(config_table: str) -> SpokeRegistrationEnvironment:
    return SpokeRegistrationEnvironment(
        config_table_name=config_table,
        enable_debug_logging=True,
        log_group="log_group",
        topic_arn="topic_arn",
        user_agent_extra="user_agent_extra",
    )


def test_registration_request_adds_account(
    config_item_store: DdbConfigItemStore,
    spoke_registration_env: SpokeRegistrationEnvironment,
) -> None:
    account_id = "111122223333"
    handler = SpokeRegistrationHandler(
        registration_request(account_id), spoke_registration_env, MockLogger()
    )

    result = handler.handle_request()

    assert result == f"Registered spoke account {account_id}"
    assert config_item_store.get().remote_account_ids == [account_id]


def test_deletion_request_removes_account(
    config_item_store: DdbConfigItemStore,
    spoke_registration_env: SpokeRegistrationEnvironment,
) -> None:
    account_id = "111122223333"
    config_item_store.register_spoke_accounts({account_id})
    handler = SpokeRegistrationHandler(
        deregistration_request(account_id), spoke_registration_env, MockLogger()
    )

    result = handler.handle_request()

    assert result == f"Deregistered spoke account {account_id}"
    assert config_item_store.get().remote_account_ids == []


def test_deletion_request_does_not_fail_if_account_does_not_exist(
    config_item_store: DdbConfigItemStore,
    spoke_registration_env: SpokeRegistrationEnvironment,
) -> None:
    account_id = "111122223333"
    handler = SpokeRegistrationHandler(
        deregistration_request(account_id), spoke_registration_env, MockLogger()
    )

    result = handler.handle_request()

    assert result == f"Deregistered spoke account {account_id}"
    assert config_item_store.get().remote_account_ids == []


@pytest.mark.parametrize(
    "operation",
    ["Register", "Deregister"],
)
def test_validate_spoke_request_success(operation: str) -> None:
    spoke_registration_request = {"account": "111111111111", "operation": operation}
    validate_spoke_request(spoke_registration_request)


def test_validate_spoke_request_invalid_account() -> None:
    with pytest.raises(ValidationException):
        spoke_registration_request = {"account": None, "operation": "Register"}
        validate_spoke_request(spoke_registration_request)


def test_validate_spoke_request_invalid_operation() -> None:
    with pytest.raises(ValidationException):
        spoke_registration_request = {
            "account": "111111111111",
            "operation": "INVALID_OPERATION",
        }
        validate_spoke_request(spoke_registration_request)
