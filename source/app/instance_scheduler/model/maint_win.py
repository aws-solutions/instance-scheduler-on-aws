# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from dataclasses import dataclass
from datetime import datetime
from re import fullmatch
from typing import TYPE_CHECKING, Final
from zoneinfo import ZoneInfo

from dateutil.parser import isoparse

from instance_scheduler.util.time import is_aware

if TYPE_CHECKING:
    from mypy_boto3_dynamodb.type_defs import (
        AttributeValueTypeDef,
        GetItemOutputTypeDef,
    )
    from mypy_boto3_ssm.type_defs import MaintenanceWindowIdentityTypeDef
else:
    AttributeValueTypeDef = object
    GetItemOutputTypeDef = object
    MaintenanceWindowIdentityTypeDef = object


class EC2SSMMaintenanceWindowValidationError(Exception):
    """An error occurred while validating the consistency of the maintenance window"""


@dataclass(frozen=True)
class EC2SSMMaintenanceWindow:
    """
    Model representing a maintenance window for an EC2 instance implemented by AWS SSM.

    Instance Scheduler treats the window name as a unique ID but the service allows
    multiple windows with the same name to be created.

    Attributes:
        account_id: 12-digit AWS account ID
        region: name of the region in which the window is defined
        window_id: the unique ID of the window as defined by the SSM service
        window_name: the user-provided name of the window
        schedule_timezone: the user-provided timezone of the window (default UTC)
        next_execution_time: the service-calculated next beginning time of the window
        duration: the duration of the window in hours
    """

    account_id: str
    region: str
    window_id: str
    window_name: str
    schedule_timezone: ZoneInfo
    next_execution_time: datetime
    duration: int

    def __post_init__(self) -> None:
        self._validate()

    def _validate(self) -> None:
        # https://docs.aws.amazon.com/systems-manager/latest/APIReference/API_CreateMaintenanceWindow.html
        if not fullmatch(r"\d{12}", self.account_id):
            raise EC2SSMMaintenanceWindowValidationError(
                f"Invalid account id: {self.account_id}"
            )
        if not len(self.region):
            raise EC2SSMMaintenanceWindowValidationError("Empty region name")
        if not fullmatch(r"mw-[0-9a-f]{17}", self.window_id):
            raise EC2SSMMaintenanceWindowValidationError(
                f"Invalid window ID: {self.window_id}"
            )
        if not fullmatch(r"[a-zA-Z0-9_\-.]{3,128}", self.window_name):
            raise EC2SSMMaintenanceWindowValidationError(
                f"Invalid maintenance window name: {self.window_name}"
            )
        if not is_aware(self.next_execution_time):
            raise EC2SSMMaintenanceWindowValidationError(
                f"Non-timezone-aware datetime: {self.next_execution_time}"
            )
        if self.duration < 1 or self.duration > 24:
            raise EC2SSMMaintenanceWindowValidationError(
                f"Invalid duration: {self.duration}"
            )

    def to_item(self) -> dict[str, AttributeValueTypeDef]:
        """Return this object as a dict suitable for a call to DynamoDB `put_item`"""
        # This definition is consistent with the old behavior, except that
        # `NextExecutionTime` is encoded using `isoformat`, which produces a stricter
        # output than the SSM service.
        return {
            "account-region": {"S": f"{self.account_id}:{self.region}"},
            "WindowId": {"S": self.window_id},
            "Name": {"S": self.window_name},
            "ScheduleTimezone": {"S": str(self.schedule_timezone)},
            "NextExecutionTime": {"S": self.next_execution_time.isoformat()},
            "Duration": {"N": str(self.duration)},
        }

    def to_key(self) -> dict[str, str]:
        """Return this object as a key suitable for a call to DynamoDB `delete_item`"""
        return {
            "account-region": f"{self.account_id}:{self.region}",
            "Name": self.window_name,
        }

    @classmethod
    def from_identity(
        cls, *, identity: MaintenanceWindowIdentityTypeDef, account_id: str, region: str
    ) -> "EC2SSMMaintenanceWindow":
        """
        Return a maintenancw window object from an SSM `describe_maintenance_windows`
        response
        """
        # It is critical to use `dateutil.parser.isoparse` to parse `NextExecutionTime`
        # and not `datetime.datetime.fromisoformat` because `fromisoformat` only
        # correctly # handles the output of `isoformat`. SSM can output either of the
        # following, # depending on if the user provided a timezone when creating the
        # window:
        # - "2023-06-27T00:00Z"
        # - "2023-06-27T03:00-04:00"
        # Both of these are valid ISO 8601 formatted timestamps, but `fromisoformat` can
        # not parse the zero-UTC-offset timezone shorthand format "Z".
        return EC2SSMMaintenanceWindow(
            account_id=account_id,
            region=region,
            window_id=identity["WindowId"],
            window_name=identity["Name"],
            schedule_timezone=ZoneInfo(identity.get("ScheduleTimezone", "UTC")),
            next_execution_time=isoparse(identity["NextExecutionTime"]),
            duration=identity["Duration"],
        )

    @classmethod
    def from_item(cls, item: GetItemOutputTypeDef) -> "EC2SSMMaintenanceWindow":
        """Return a maintenance window object from a DynamoDB `get_item` response"""
        # Like `from_identity`, this function must use `isoparse` to parse
        # `next_execution_time` because Instance Scheduler may have stored the value
        # from the service response verbatim.
        account_region: Final = item["Item"]["account-region"]["S"].split(":")
        return EC2SSMMaintenanceWindow(
            account_id=account_region[0],
            region=account_region[1],
            window_id=item["Item"]["WindowId"]["S"],
            window_name=item["Item"]["Name"]["S"],
            schedule_timezone=ZoneInfo(item["Item"]["ScheduleTimezone"]["S"]),
            next_execution_time=isoparse(item["Item"]["NextExecutionTime"]["S"]),
            duration=int(item["Item"]["Duration"]["N"]),
        )
