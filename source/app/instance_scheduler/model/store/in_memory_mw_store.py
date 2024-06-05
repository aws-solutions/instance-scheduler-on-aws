# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from typing import Iterator, Mapping, Optional

from instance_scheduler.model import EC2SSMMaintenanceWindow, MWStore

AccountRegionPK = str
NameIDSK = str


class InMemoryMWStore(MWStore):

    _data: dict[AccountRegionPK, dict[NameIDSK, EC2SSMMaintenanceWindow]]

    def __init__(
        self,
        initial_data: Optional[
            Mapping[AccountRegionPK, dict[NameIDSK, EC2SSMMaintenanceWindow]]
        ] = None,
    ):
        self._data = dict(initial_data) if initial_data else dict()

    def put(self, window: EC2SSMMaintenanceWindow) -> None:
        if window.account_region not in self._data:
            self._data[window.account_region] = dict()
        self._data[window.account_region][window.name_id] = window

    def delete(self, window: EC2SSMMaintenanceWindow) -> None:
        if window.account_region in self._data:
            self._data[window.account_region].pop(window.name_id)

    def find_by_account_region(
        self, account: str, region: str
    ) -> Iterator[EC2SSMMaintenanceWindow]:
        account_region = to_account_region_pk(account, region)
        if account_region in self._data:
            return iter(self._data[account_region].values())
        else:
            return iter([])


def to_account_region_pk(account: str, region: str) -> AccountRegionPK:
    return f"{account}:{region}"
