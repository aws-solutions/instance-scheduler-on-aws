# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from dataclasses import dataclass
from typing import Final, Iterable, Optional

from instance_scheduler.configuration.scheduling_context import SchedulingContext
from instance_scheduler.maint_win.ssm_mw_client import SSMMWClient
from instance_scheduler.model import EC2SSMMaintenanceWindow, MWStore
from instance_scheduler.model.store.in_memory_mw_store import (
    InMemoryMWStore,
    to_account_region_pk,
)
from instance_scheduler.util.logger import Logger
from instance_scheduler.util.session_manager import AssumedRole


@dataclass(frozen=True)
class MWDeltas:
    unchanged: dict[str, EC2SSMMaintenanceWindow]
    updated: dict[str, EC2SSMMaintenanceWindow]
    deleted: dict[str, EC2SSMMaintenanceWindow]


class MaintenanceWindowContext:
    """
    Interface Abstraction for working with EC2 Maintenance Windows within the context
    of a specific scheduling target (account/region)

    Expected use of this context would be to invoke reconcile_with_dynamo_db() exactly once at the beginning
    of each scheduling request. This will then synchronize maintenance windows stored in the maint_win ddb table
    with those reported by the SSM service in that given scheduling target.

    The reason for this data duplication is to work around a limitation in the SSM Maintenance Window API:
    When calling describe_maintenance_windows on the SSM api, The information returned for each maintenance window
    includes the window duration (in hours) and the next_execution_time (datetime) for that window. This tells us
    when the next window will run, but not when the most recent window execution (which may still be running)
    last started. As such, we must maintain a separate record of maintenance windows that can track the most recent
    execution in order to remember that a 3-hour maintenance window that started an hour ago
    will still be active for the next 2 hours. Only after the previous maintenance window has ended can we discard that
    information and replace it with the next planned window
    """

    _context: Final[SchedulingContext]
    _spoke_scheduler_role: Final[AssumedRole]
    _ddb_store: Final[MWStore]

    _prefetched_windows: Optional[dict[str, list[EC2SSMMaintenanceWindow]]] = None

    def __init__(
        self,
        scheduling_context: SchedulingContext,
        spoke_scheduler_role: AssumedRole,
        mw_store: MWStore,
        logger: Logger,
    ):
        self._context = scheduling_context
        self._spoke_scheduler_role = spoke_scheduler_role
        self._ssm_mw_client = SSMMWClient(spoke_scheduler_role)
        self._ddb_store = mw_store
        self._logger = logger

    def reconcile_ssm_with_dynamodb(self) -> None:
        """
        fetch all maintenance windows in the given context and reconcile them with the windows being tracked in
        dynamodb. The purpose of this table is to remember actively running windows that the SSM api is unable to return
        (it only provides info about the next execution in the future) As such, any windows stored in dynamodb and
        currently in a running state need to be preserved until after the running window has concluded
        """
        self._logger.info(
            "Beginning reconciliation of maintenance windows between SSM and DDB"
        )
        account = self._context.account_id
        region = self._context.region

        raw_ssm_data = SSMMWClient(self._spoke_scheduler_role).get_mws_from_ssm()
        filtered_ssm_data = _collect_by_nameid(
            self.filter_by_windows_defined_in_schedules(
                self.filter_by_windows_with_next_execution_time(raw_ssm_data)
            )
        )

        ddb_data = _collect_by_nameid(
            self._ddb_store.find_by_account_region(account, region)
        )

        # in-mem store to mirror changes made to ddb
        in_mem_store = InMemoryMWStore(
            {to_account_region_pk(account, region): ddb_data}
        )

        deltas = _compute_delta_between(original=ddb_data, new=filtered_ssm_data)

        # if the window currently stored in dynamodb is still running, we need to respect that window
        # until it stops
        for updated_window in deltas.updated.values():
            if self._is_running(ddb_data.get(updated_window.name_id)):
                continue  # reject the update

            try:
                self._ddb_store.put(updated_window)
                in_mem_store.put(updated_window)
            except Exception as e:
                self._logger.error(
                    f"error updating maintenance window {updated_window.name_id} -- skipping update. Error: {e}"
                )

        for deleted_window in deltas.deleted.values():
            if self._is_running(ddb_data.get(deleted_window.name_id)):
                continue  # reject the update

            try:
                self._ddb_store.delete(deleted_window)  # update window in ddb
                in_mem_store.delete(deleted_window)
            except Exception as e:
                self._logger.error(
                    f"error deleting maintenance window {deleted_window.name_id} -- skipping delete. Error: {e}"
                )

        # reset cache
        self._prefetched_windows = _collect_and_aggregate_by_name(
            in_mem_store.find_by_account_region(account, region)
        )

        self._logger.info(
            f"reconciliation complete! updated: {len(deltas.updated)}, "
            f"deleted: {len(deltas.deleted)}, "
            f"total_windows_loaded: {sum([len(mws) for mws in self._prefetched_windows.values()])}"
        )

    def _is_running(self, window: Optional[EC2SSMMaintenanceWindow]) -> bool:
        if not window:
            return False
        return window.is_running_at(
            self._context.current_dt, self._context.scheduling_interval_minutes
        )

    def __contains__(self, name: str) -> bool:
        return bool(self.find_by_name(name))

    def find_by_name(self, name: str) -> Iterable[EC2SSMMaintenanceWindow]:
        if not self._windows_loaded():
            self.reconcile_ssm_with_dynamodb()
        assert self._prefetched_windows is not None
        return self._prefetched_windows.get(name, [])

    def _windows_loaded(self) -> bool:
        return self._prefetched_windows is not None

    def filter_by_windows_defined_in_schedules(
        self, windows: Iterable[EC2SSMMaintenanceWindow]
    ) -> Iterable[EC2SSMMaintenanceWindow]:

        # collect all windows referenced by schedules
        referenced_windows: set[str] = set()
        for schedule in self._context.schedules.values():
            if schedule.ssm_maintenance_window:
                referenced_windows.update(schedule.ssm_maintenance_window)

        for window in windows:
            if window.window_name in referenced_windows:
                yield window

    def filter_by_windows_with_next_execution_time(
        self, windows: Iterable[EC2SSMMaintenanceWindow]
    ) -> Iterable[EC2SSMMaintenanceWindow]:
        for window in windows:
            if window.next_execution_time:
                yield window


def _compute_delta_between(
    original: dict[str, EC2SSMMaintenanceWindow],
    new: dict[str, EC2SSMMaintenanceWindow],
) -> MWDeltas:
    """
    compare 2 dict[name-id, maintenance-window] and return the delta of what has been
    updated/deleted from the original to the new dict
    """

    unchanged: dict[str, EC2SSMMaintenanceWindow] = dict()
    updated: dict[str, EC2SSMMaintenanceWindow] = dict()
    deleted: dict[str, EC2SSMMaintenanceWindow] = dict()

    for new_window in new.values():
        if new_window == original.get(new_window.name_id, None):
            unchanged[new_window.name_id] = new_window
        else:
            updated[new_window.name_id] = new_window

    for og_window in original.values():
        if og_window.name_id not in new:
            deleted[og_window.name_id] = og_window

    return MWDeltas(unchanged, updated, deleted)


def _collect_by_nameid(
    maintenance_windows: Iterable[EC2SSMMaintenanceWindow],
) -> dict[str, EC2SSMMaintenanceWindow]:
    """
    collect an iterable of MWs into a dict of the form [name-id, EC2SSMMaintenanceWindow]
    this function assumes that all name-ids are unique which is true only within a specific account-region, thus
    this function should only be used within single target contexts
    """
    return {mw.name_id: mw for mw in maintenance_windows}


def _collect_and_aggregate_by_name(
    maintenance_windows: Iterable[EC2SSMMaintenanceWindow],
) -> dict[str, list[EC2SSMMaintenanceWindow]]:
    """
    collect an iterable of MWs into a dict of the form [name, list[EC2SSMMaintenanceWindow]]
    """
    result: dict[str, list[EC2SSMMaintenanceWindow]] = dict()
    for mw in maintenance_windows:
        if mw.window_name not in result:
            result[mw.window_name] = [mw]
        else:
            result[mw.window_name].append(mw)

    return result
