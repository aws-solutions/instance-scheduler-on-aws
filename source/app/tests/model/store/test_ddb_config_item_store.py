# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from _pytest.fixtures import fixture

from instance_scheduler.model.ddb_config_item import DdbConfigItem
from instance_scheduler.model.store.ddb_config_item_store import DdbConfigItemStore
from tests.test_utils.unordered_list import UnorderedList


@fixture
def config_item_store(config_table: str) -> DdbConfigItemStore:
    return DdbConfigItemStore(config_table)


def test_write_then_read(config_item_store: DdbConfigItemStore) -> None:
    config_item = DdbConfigItem(
        remote_account_ids=["111122223333", "222233334444"],
        organization_id="some_org_id",
    )

    config_item_store.put(config_item)
    fetched = config_item_store.get()
    assert fetched == config_item


def test_account_ids_with_no_org_id(config_item_store: DdbConfigItemStore) -> None:
    config_item = DdbConfigItem(
        remote_account_ids=["111122223333", "222233334444"],
    )

    config_item_store.put(config_item)
    fetched = config_item_store.get()
    assert fetched == config_item


def test_org_id_with_no_remote_accounts(config_item_store: DdbConfigItemStore) -> None:
    config_item = DdbConfigItem(organization_id="some_org_id")

    config_item_store.put(config_item)
    fetched = config_item_store.get()
    assert fetched == config_item


def test_empty_config_item(config_item_store: DdbConfigItemStore) -> None:
    config_item = DdbConfigItem()

    config_item_store.put(config_item)
    fetched = config_item_store.get()
    assert fetched == config_item


def test_config_with_ssm_param_references(
    config_item_store: DdbConfigItemStore,
) -> None:
    config_item = DdbConfigItem(
        remote_account_ids=["{param:my_ssm_param}", "222233334444"],
    )

    config_item_store.put(config_item)
    fetched = config_item_store.get()
    assert fetched == config_item


def test_register_spoke_account(config_item_store: DdbConfigItemStore) -> None:
    account_id = "111122223333"
    result = config_item_store.register_spoke_accounts({account_id})
    assert result.remote_account_ids == [account_id]
    assert config_item_store.get().remote_account_ids == [account_id]


def test_register_spoke_account_does_not_create_duplicates(
    config_item_store: DdbConfigItemStore,
) -> None:
    account_id = "111122223333"

    config_item_store.register_spoke_accounts({account_id})
    result = config_item_store.register_spoke_accounts({account_id})

    assert result.remote_account_ids == [account_id]
    assert config_item_store.get().remote_account_ids == [account_id]


def test_register_multiple_spoke_accounts(
    config_item_store: DdbConfigItemStore,
) -> None:
    account_ids = {"111122223333", "222233334444", "123456789012"}
    result = config_item_store.register_spoke_accounts(account_ids)
    assert result.remote_account_ids == UnorderedList(account_ids)
    assert config_item_store.get().remote_account_ids == UnorderedList(account_ids)


def test_deregister_spoke_account(config_item_store: DdbConfigItemStore) -> None:
    account_id = "111122223333"
    config_item_store.register_spoke_accounts({account_id})

    result = config_item_store.deregister_spoke_accounts({account_id})

    assert result.remote_account_ids == []
    assert config_item_store.get().remote_account_ids == []


def test_deregister_spoke_account_does_not_throw_error_when_not_exists(
    config_item_store: DdbConfigItemStore,
) -> None:
    result = config_item_store.deregister_spoke_accounts({"111122223333"})
    assert result.remote_account_ids == []


def test_deregister_multiple_spoke_accounts(
    config_item_store: DdbConfigItemStore,
) -> None:
    account_ids = {"111122223333", "222233334444", "123456789012"}
    config_item_store.register_spoke_accounts(account_ids)

    result = config_item_store.deregister_spoke_accounts(account_ids)

    assert result.remote_account_ids == []
    assert config_item_store.get().remote_account_ids == []


def test_deregister_multiple_spoke_accounts_deletes_all_that_exist(
    config_item_store: DdbConfigItemStore,
) -> None:
    account_ids = {"111122223333", "222233334444", "123456789012"}
    config_item_store.register_spoke_accounts({"111122223333"})

    result = config_item_store.deregister_spoke_accounts(account_ids)

    assert result.remote_account_ids == []
    assert config_item_store.get().remote_account_ids == []
