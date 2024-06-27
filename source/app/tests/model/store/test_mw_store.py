# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from _pytest.fixtures import SubRequest, fixture

from instance_scheduler.model import EC2SSMMaintenanceWindow, MWStore
from instance_scheduler.model.store.dynamo_mw_store import DynamoMWStore
from instance_scheduler.model.store.in_memory_mw_store import InMemoryMWStore
from tests.integration.helpers.schedule_helpers import quick_time

# defaults used for tests that don't explicitly need to control the account/region
account = "123456789012"
region = "us-east-1"


@fixture(params=["dynamo", "in-memory"])
def mw_store(request: SubRequest) -> MWStore:
    match request.param:
        case "dynamo":
            return DynamoMWStore(request.getfixturevalue(argname="maint_win_table"))
        case "in-memory":
            return InMemoryMWStore()
        case _:
            raise ValueError()


def new_mw(
    window_id: str,
    account_id: str = account,
    region: str = region,
    window_name: str = "test-window",
    schedule_timezone: ZoneInfo = ZoneInfo("UTC"),
    next_execution_time: Optional[datetime] = quick_time(12, 0, 0),
    duration_hours: int = 1,
) -> EC2SSMMaintenanceWindow:
    return EC2SSMMaintenanceWindow(
        account_id=account_id,
        region=region,
        window_id=window_id,
        window_name=window_name,
        schedule_timezone=schedule_timezone,
        next_execution_time=next_execution_time,
        duration_hours=duration_hours,
    )


def test_write_then_read_mw(mw_store: MWStore) -> None:
    mw1 = new_mw("mw-00000000000000000")
    mw2 = new_mw("mw-00000000000000012")
    mw_store.put(mw1)
    mw_store.put(mw2)

    fetched_result = list(mw_store.find_by_account_region(account, region))

    assert len(fetched_result) == 2
    assert mw1 in fetched_result
    assert mw2 in fetched_result


def test_put_overwrites_existing_mw(mw_store: MWStore) -> None:
    # note: account_id, region, window_id, and window_name are all part of the unique key of a window
    # thus these are all considered different windows for the db. the most common thing that will change
    # and require an overwrite is the next_execution_time
    orig = new_mw("mw-00000000000000000", next_execution_time=quick_time(10, 0, 0))
    replacement = new_mw(
        "mw-00000000000000000", next_execution_time=quick_time(20, 0, 0)
    )
    mw_store.put(orig)
    mw_store.put(replacement)

    fetched_result = list(mw_store.find_by_account_region(account, region))
    assert len(fetched_result) == 1
    assert fetched_result[0] == replacement
    assert fetched_result[0] != orig


def test_delete_mw_deletes_correctly(mw_store: MWStore) -> None:
    mw = new_mw("mw-00000000000000000")
    mw_store.put(mw)

    assert len(list(mw_store.find_by_account_region(account, region))) == 1

    mw_store.delete(mw)
    assert len(list(mw_store.find_by_account_region(account, region))) == 0


def test_delete_mw_doesnt_error_when_mw_does_not_exist(mw_store: MWStore) -> None:
    mw = new_mw("mw-00000000000000000")
    mw_store.delete(mw)
