# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from typing import TYPE_CHECKING, Final, Iterator

from instance_scheduler.model import EC2SSMMaintenanceWindow
from instance_scheduler.util.session_manager import AssumedRole

if TYPE_CHECKING:
    from mypy_boto3_ssm import SSMClient
else:
    SSMClient = object


class SSMMWClient:

    def __init__(self, spoke_session: AssumedRole):
        self._spoke_session = spoke_session

    def get_mws_from_ssm(self) -> Iterator[EC2SSMMaintenanceWindow]:
        """
        This function gets all the ssm windows which are enabled from SSM service.

        Returns:
            list of ssm windows
        """
        ssm: Final[SSMClient] = self._spoke_session.client("ssm")
        paginator: Final = ssm.get_paginator("describe_maintenance_windows")
        for page in paginator.paginate(
            Filters=[{"Key": "Enabled", "Values": ["true"]}]
        ):
            for identity in page["WindowIdentities"]:
                yield EC2SSMMaintenanceWindow.from_identity(
                    identity=identity,
                    account_id=self._spoke_session.account,
                    region=self._spoke_session.region,
                )
