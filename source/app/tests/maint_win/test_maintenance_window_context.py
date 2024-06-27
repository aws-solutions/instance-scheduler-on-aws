# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterable, Iterator, Optional
from unittest.mock import patch
from zoneinfo import ZoneInfo

from instance_scheduler.configuration.instance_schedule import InstanceSchedule
from instance_scheduler.maint_win.maintenance_window_context import (
    MaintenanceWindowContext,
)
from instance_scheduler.maint_win.ssm_mw_client import SSMMWClient
from instance_scheduler.model import EC2SSMMaintenanceWindow, MWStore
from instance_scheduler.util.session_manager import AssumedRole
from tests.integration.helpers.schedule_helpers import quick_time
from tests.integration.helpers.scheduling_context_builder import (
    build_scheduling_context,
)
from tests.logger import MockLogger
from tests.model.store.test_mw_store import new_mw


def test_find_by_name_returns_all_windows_with_same_name(
    mw_store: MWStore, hub_role: AssumedRole
) -> None:
    a_windows = [
        new_mw("mw-00000000000000000", window_name="aaa"),
        new_mw("mw-00000000000000001", window_name="aaa"),
        new_mw("mw-00000000000000002", window_name="aaa"),
    ]

    b_windows = [
        new_mw("mw-00000000000000003", window_name="bbb"),
        new_mw("mw-00000000000000004", window_name="bbb"),
    ]

    with ssm_returning(a_windows + b_windows):
        mw_context = new_mw_context(
            mw_store, hub_role, mws_referenced_by_schedules=a_windows + b_windows
        )

        fetched_a_windows = mw_context.find_by_name("aaa")
        fetched_b_windows = mw_context.find_by_name("bbb")

        assert all(a_window in fetched_a_windows for a_window in a_windows)
        assert all(b_window not in fetched_a_windows for b_window in b_windows)
        assert all(a_window not in fetched_b_windows for a_window in a_windows)
        assert all(b_window in fetched_b_windows for b_window in b_windows)


def test_contains_returns_false_on_empty_context(
    mw_store: MWStore, hub_role: AssumedRole
) -> None:
    mw_context = new_mw_context(mw_store, hub_role)
    assert "some_value" not in mw_context


def test_contains_returns_true_when_name_has_at_least_1_associated_mw(
    mw_store: MWStore, hub_role: AssumedRole
) -> None:
    windows = [
        new_mw("mw-00000000000000001", window_name="named_window"),
        new_mw("mw-00000000000000002", window_name="shared_name"),
        new_mw("mw-00000000000000003", window_name="shared_name"),
    ]
    with ssm_returning(windows):
        mw_context = new_mw_context(
            mw_store, hub_role, mws_referenced_by_schedules=windows
        )

        assert "shared_name" in mw_context
        assert "named_window" in mw_context
        assert "missing" not in mw_context


def test_find_by_name_returns_empty_list_when_no_windows_found(
    mw_store: MWStore, hub_role: AssumedRole
) -> None:
    mw_context = new_mw_context(mw_store, hub_role)

    assert list(mw_context.find_by_name("unknown")) == []


def test_reconcile_adds_new_mws_to_db(mw_store: MWStore, hub_role: AssumedRole) -> None:
    with ssm_returning([new_mw("mw-00000000000000000")]):
        new_mw_context(mw_store, hub_role).reconcile_ssm_with_dynamodb()

        db_mws = list(
            mw_store.find_by_account_region(hub_role.account, hub_role.region)
        )
        assert len(db_mws) == 1


def test_reconcile_filters_out_windows_not_referenced_by_at_least_one_schedule(
    mw_store: MWStore, hub_role: AssumedRole
) -> None:
    referenced_window = new_mw("mw-00000000000000000", window_name="referenced")
    not_referenced_window = new_mw("mw-00000000000000001", window_name="not-referenced")
    with ssm_returning([referenced_window, not_referenced_window]):
        new_mw_context(
            mw_store, hub_role, mws_referenced_by_schedules=[referenced_window]
        ).reconcile_ssm_with_dynamodb()

        db_mws = list(
            mw_store.find_by_account_region(hub_role.account, hub_role.region)
        )
        assert referenced_window in db_mws
        assert not_referenced_window not in db_mws


def test_reconcile_deletes_windows_no_longer_referenced_by_at_least_one_schedule(
    mw_store: MWStore, hub_role: AssumedRole
) -> None:
    referenced_window = new_mw("mw-00000000000000000", window_name="referenced")
    not_referenced_window = new_mw("mw-00000000000000001", window_name="not-referenced")
    mw_store.put(not_referenced_window)  # put window into db
    with ssm_returning([referenced_window, not_referenced_window]):
        new_mw_context(
            mw_store, hub_role, mws_referenced_by_schedules=[referenced_window]
        ).reconcile_ssm_with_dynamodb()

        db_mws = list(
            mw_store.find_by_account_region(hub_role.account, hub_role.region)
        )
        assert (
            referenced_window in db_mws
        )  # validate that delete was only on the non-referenced window
        assert not_referenced_window not in db_mws


def test_reconcile_updates_mws_in_db_when_existing_window_is_not_active(
    mw_store: MWStore, hub_role: AssumedRole
) -> None:
    old_window = new_mw(
        "mw-00000000000000001",
        next_execution_time=quick_time(10, 0, 0),
        duration_hours=2,
    )
    next_window = new_mw(
        "mw-00000000000000001",
        next_execution_time=quick_time(20, 0, 0),
        duration_hours=2,
    )
    mw_store.put(old_window)

    with ssm_returning([next_window]):
        new_mw_context(
            mw_store, hub_role, current_dt=quick_time(15, 0, 0)
        ).reconcile_ssm_with_dynamodb()

        db_mws = list(
            mw_store.find_by_account_region(hub_role.account, hub_role.region)
        )
        assert len(db_mws) == 1
        assert old_window not in db_mws
        assert next_window in db_mws


def test_reconcile_removes_windows_from_db_that_are_no_longer_in_ssm(
    mw_store: MWStore, hub_role: AssumedRole
) -> None:
    window_to_be_preserved = new_mw("mw-00000000000000001")
    window_to_be_deleted = new_mw("mw-00000000000000002")

    mw_store.put(window_to_be_deleted)
    mw_store.put(window_to_be_preserved)

    with ssm_returning([window_to_be_preserved]):
        new_mw_context(mw_store, hub_role).reconcile_ssm_with_dynamodb()

        db_mws = list(
            mw_store.find_by_account_region(hub_role.account, hub_role.region)
        )
        assert len(db_mws) == 1
        assert window_to_be_preserved in db_mws
        assert window_to_be_deleted not in db_mws


def test_reconcile_does_not_delete_windows_that_are_still_running_until_they_stop(
    mw_store: MWStore, hub_role: AssumedRole
) -> None:
    running_window = new_mw(
        "mw-00000000000000001",
        next_execution_time=quick_time(10, 0, 0),
        duration_hours=5,
    )
    mw_store.put(running_window)

    with ssm_returning([]):
        # window running
        new_mw_context(
            mw_store, hub_role, current_dt=quick_time(11, 0, 0)
        ).reconcile_ssm_with_dynamodb()

        assert running_window in mw_store.find_by_account_region(
            hub_role.account, hub_role.region
        )

        # window stopped
        new_mw_context(
            mw_store, hub_role, current_dt=quick_time(15, 0, 0)
        ).reconcile_ssm_with_dynamodb()

        assert running_window not in mw_store.find_by_account_region(
            hub_role.account, hub_role.region
        )


def test_reconcile_does_not_overwrite_windows_that_are_still_running_until_they_stop(
    mw_store: MWStore, hub_role: AssumedRole
) -> None:
    running_window = new_mw(
        "mw-00000000000000001",
        next_execution_time=datetime(2024, 5, 15, 10, 0, 0, tzinfo=timezone.utc),
        duration_hours=5,
    )
    next_window = new_mw(
        "mw-00000000000000001",
        next_execution_time=datetime(2024, 5, 16, 10, 0, 0, tzinfo=timezone.utc),
        duration_hours=5,
    )
    mw_store.put(running_window)

    with ssm_returning([next_window]):
        # window running
        new_mw_context(
            mw_store,
            hub_role,
            current_dt=datetime(2024, 5, 15, 11, 0, 0, tzinfo=timezone.utc),
        ).reconcile_ssm_with_dynamodb()

        assert running_window in mw_store.find_by_account_region(
            hub_role.account, hub_role.region
        )
        assert next_window not in mw_store.find_by_account_region(
            hub_role.account, hub_role.region
        )

        # window stopped
        new_mw_context(
            mw_store,
            hub_role,
            current_dt=datetime(2024, 5, 15, 15, 0, 0, tzinfo=timezone.utc),
        ).reconcile_ssm_with_dynamodb()

        db_mws = list(
            mw_store.find_by_account_region(hub_role.account, hub_role.region)
        )
        assert len(db_mws) == 1
        assert running_window not in db_mws
        assert next_window in db_mws


def test_find_windows_after_reconcile_matches_contents_of_db(
    mw_store: MWStore, hub_role: AssumedRole
) -> None:
    window_to_be_added = new_mw("mw-00000000000000000")
    window_to_be_preserved = new_mw("mw-00000000000000001")
    window_to_be_deleted = new_mw("mw-00000000000000002")
    window_to_be_overwritten = new_mw("mw-00000000000000003", duration_hours=2)
    window_to_be_updated = new_mw("mw-00000000000000003", duration_hours=5)
    window_not_referenced_by_schedule = new_mw(
        "mw-00000000000000004", window_name="not-referenced"
    )

    mw_store.put(window_to_be_deleted)
    mw_store.put(window_to_be_preserved)
    mw_store.put(window_to_be_overwritten)

    with ssm_returning(
        [window_to_be_added, window_to_be_preserved, window_to_be_updated]
    ):
        mw_context = new_mw_context(mw_store, hub_role)
        mw_context.reconcile_ssm_with_dynamodb()

        db_mws = list(
            mw_store.find_by_account_region(hub_role.account, hub_role.region)
        )

        # check assert for each action
        assert window_to_be_added in db_mws
        assert window_to_be_added in mw_context.find_by_name(
            window_to_be_added.window_name
        )

        assert window_to_be_preserved in db_mws
        assert window_to_be_preserved in mw_context.find_by_name(
            window_to_be_preserved.window_name
        )

        assert window_to_be_updated in db_mws
        assert window_to_be_updated in mw_context.find_by_name(
            window_to_be_updated.window_name
        )

        assert window_to_be_overwritten not in db_mws
        assert window_to_be_overwritten not in mw_context.find_by_name(
            window_to_be_overwritten.window_name
        )

        assert window_to_be_deleted not in db_mws
        assert window_to_be_deleted not in mw_context.find_by_name(
            window_to_be_deleted.window_name
        )

        assert window_not_referenced_by_schedule not in db_mws
        assert window_not_referenced_by_schedule not in mw_context.find_by_name(
            window_not_referenced_by_schedule.window_name
        )


def test_does_not_process_maintenance_windows_without_next_execution_time(
    mw_store: MWStore, hub_role: AssumedRole
) -> None:
    window_with_execution_time = new_mw("mw-00000000000000000")
    window_without_execution_time = new_mw(
        "mw-00000000000000001", next_execution_time=None
    )

    with ssm_returning([window_with_execution_time, window_without_execution_time]):
        mw_context = new_mw_context(mw_store, hub_role)
        mw_context.reconcile_ssm_with_dynamodb()

        db_mws = list(
            mw_store.find_by_account_region(hub_role.account, hub_role.region)
        )

        # check assert for each action
        assert window_with_execution_time in db_mws
        assert window_with_execution_time in mw_context.find_by_name(
            window_with_execution_time.window_name
        )

        assert window_without_execution_time not in db_mws
        assert window_without_execution_time not in mw_context.find_by_name(
            window_without_execution_time.window_name
        )


def test_does_not_delete_running_windows_with_no_next_execution_time_until_they_stopped(
    mw_store: MWStore, hub_role: AssumedRole
) -> None:
    window = new_mw(
        "mw-00000000000000001",
        next_execution_time=quick_time(10, 0, 0),
        duration_hours=5,
    )
    mw_store.put(window)

    window_no_next_execution_time = new_mw(
        "mw-00000000000000001",
        next_execution_time=None,
        duration_hours=5,
    )

    with ssm_returning([window_no_next_execution_time]):
        # window running
        new_mw_context(
            mw_store, hub_role, current_dt=quick_time(11, 0, 0)
        ).reconcile_ssm_with_dynamodb()

        assert window in mw_store.find_by_account_region(
            hub_role.account, hub_role.region
        )

        # window stopped
        new_mw_context(
            mw_store, hub_role, current_dt=quick_time(15, 0, 0)
        ).reconcile_ssm_with_dynamodb()

        assert window not in mw_store.find_by_account_region(
            hub_role.account, hub_role.region
        )
        assert window_no_next_execution_time not in mw_store.find_by_account_region(
            hub_role.account, hub_role.region
        )


def new_mw_context(
    mw_store: MWStore,
    hub_role: AssumedRole,
    current_dt: datetime = quick_time(10, 0, 0),
    mws_referenced_by_schedules: Optional[list[EC2SSMMaintenanceWindow]] = None,
) -> MaintenanceWindowContext:
    if mws_referenced_by_schedules is None:
        # make sure the default mw name is referenced by at least one schedule (simplifies tests)
        mws_referenced_by_schedules = [new_mw("mw-11112222333344445")]
    mw_schedule = InstanceSchedule(
        name="mw-schedule",
        ssm_maintenance_window=[mw.window_name for mw in mws_referenced_by_schedules],
        timezone=ZoneInfo("UTC"),
    )
    return MaintenanceWindowContext(
        scheduling_context=build_scheduling_context(
            current_dt, schedules={mw_schedule.name: mw_schedule}
        ),
        mw_store=mw_store,
        spoke_scheduler_role=hub_role,
        logger=MockLogger(),
    )


@contextmanager
def ssm_returning(mws: Iterable[EC2SSMMaintenanceWindow]) -> Iterator[None]:
    with patch.object(SSMMWClient, "get_mws_from_ssm") as ssm_endpoint:
        ssm_endpoint.return_value = mws
        yield
