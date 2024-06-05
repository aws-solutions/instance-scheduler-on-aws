# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from abc import ABC, abstractmethod
from collections.abc import Iterator

from instance_scheduler.model.maint_win import EC2SSMMaintenanceWindow


class MWStore(ABC):
    """
    An abstract DAO layer between the rest of the app and the underlying persistence engine being used to
    store SSM Maintenance Windows
    """

    @abstractmethod
    def put(self, window: EC2SSMMaintenanceWindow) -> None:
        raise NotImplementedError()

    @abstractmethod
    def delete(self, window: EC2SSMMaintenanceWindow) -> None:
        raise NotImplementedError()

    @abstractmethod
    def find_by_account_region(
        self, account: str, region: str
    ) -> Iterator[EC2SSMMaintenanceWindow]:
        raise NotImplementedError()
