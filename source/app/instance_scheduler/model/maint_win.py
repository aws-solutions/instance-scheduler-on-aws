# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from re import fullmatch
from typing import TYPE_CHECKING, Any, Final, Optional, Union
from zoneinfo import ZoneInfo

from dateutil.parser import isoparse

from instance_scheduler.configuration.instance_schedule import InstanceSchedule
from instance_scheduler.configuration.running_period import RunningPeriod
from instance_scheduler.configuration.running_period_dict_element import (
    RunningPeriodDictElement,
)
from instance_scheduler.configuration.time_utils import parse_time_str
from instance_scheduler.cron.cron_recurrence_expression import CronRecurrenceExpression
from instance_scheduler.cron.expression import CronSingleValueNumeric
from instance_scheduler.model.ddb_item_utils import skip_if_none
from instance_scheduler.schedulers.states import ScheduleState
from instance_scheduler.util.time import is_aware
from instance_scheduler.util.validation import (
    validate_number_item,
    validate_string_item,
)

if TYPE_CHECKING:
    from mypy_boto3_dynamodb.type_defs import AttributeValueTypeDef
    from mypy_boto3_ssm.type_defs import MaintenanceWindowIdentityTypeDef
else:
    AttributeValueTypeDef = object
    MaintenanceWindowIdentityTypeDef = object


ItemTypeDef = dict[
    str,
    Union[
        bytes,
        bytearray,
        str,
        int,
        Decimal,
        bool,
        set[int],
        set[Decimal],
        set[str],
        set[bytes],
        set[bytearray],
        Sequence[Any],
        Mapping[str, Any],
        None,
    ],
]

WINDOW_ID_LENGTH = 20  # window id has a fixed length of 20


class EC2SSMMaintenanceWindowValidationError(Exception):
    """An error occurred while validating the consistency of the maintenance window"""


class NoNextExecutionTimeError(Exception):
    """No next execution time could be found for the maintenance window"""


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
    next_execution_time: Optional[datetime]
    duration_hours: int

    def __post_init__(self) -> None:
        self._validate()

    @property
    def account_region(self) -> str:
        return f"{self.account_id}:{self.region}"

    @property
    def name_id(self) -> str:
        return f"{self.window_name}:{self.window_id}"

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
        if self.next_execution_time is not None and not is_aware(
            self.next_execution_time
        ):
            raise EC2SSMMaintenanceWindowValidationError(
                f"Non-timezone-aware datetime: {self.next_execution_time}"
            )
        if self.duration_hours < 1 or self.duration_hours > 24:
            raise EC2SSMMaintenanceWindowValidationError(
                f"Invalid duration: {self.duration_hours}"
            )

    def to_item(self) -> dict[str, AttributeValueTypeDef]:
        """Return this object as a dict suitable for a call to DynamoDB `put_item`"""
        # This definition is consistent with the old behavior, except that
        # `NextExecutionTime` is encoded using `isoformat`, which produces a stricter
        # output than the SSM service.
        return {
            "account-region": {"S": self.account_region},
            "name-id": {"S": self.name_id},
            "ScheduleTimezone": {"S": str(self.schedule_timezone)},
            **skip_if_none(
                "NextExecutionTime",
                {
                    "S": (
                        self.next_execution_time.isoformat()
                        if self.next_execution_time
                        else None
                    )
                },
            ),
            "Duration": {"N": str(self.duration_hours)},
        }

    def to_key(self) -> dict[str, AttributeValueTypeDef]:
        """Return this object as a key suitable for a call to DynamoDB `delete_item`"""
        return {
            "account-region": {"S": f"{self.account_id}:{self.region}"},
            "name-id": {"S": f"{self.window_name}:{self.window_id}"},
        }

    def is_running_at(self, dt: datetime, scheduler_interval_minutes: int) -> bool:
        try:
            return (
                self.to_schedule(scheduler_interval_minutes).get_desired_state(dt)[0]
                == ScheduleState.RUNNING
            )
        except NoNextExecutionTimeError:
            return False

    def to_schedule(self, scheduler_interval_minutes: int) -> InstanceSchedule:
        """convert this maintenance window into a schedule"""
        if self.next_execution_time is None:
            raise NoNextExecutionTimeError(
                f"Maintenance window {self.window_id} does not have a next_execution_time"
            )

        name_id = f"{self.window_name}:{self.window_id}"
        window_begin_dt: Final = self.next_execution_time.replace(
            second=0, microsecond=0
        )
        margin_minutes: Final = scheduler_interval_minutes + 10
        period_begin_dt: Final = window_begin_dt - timedelta(minutes=margin_minutes)
        period_end_dt: Final = window_begin_dt + timedelta(hours=self.duration_hours)

        if period_begin_dt.day == period_end_dt.day:
            periods: list[RunningPeriodDictElement] = [
                {
                    "period": RunningPeriod(
                        name=f"{name_id}-period",
                        begintime=period_begin_dt.time(),
                        endtime=period_end_dt.time(),
                        cron_recurrence=CronRecurrenceExpression(
                            monthdays=CronSingleValueNumeric(period_begin_dt.day),
                            months=CronSingleValueNumeric(period_begin_dt.month),
                        ),
                    ),
                    "instancetype": None,
                }
            ]
        elif period_end_dt - period_begin_dt <= timedelta(hours=24):
            periods = [
                {
                    "period": RunningPeriod(
                        name=f"{name_id}-period-1",
                        begintime=period_begin_dt.time(),
                        endtime=parse_time_str("23:59"),
                        cron_recurrence=CronRecurrenceExpression(
                            monthdays=CronSingleValueNumeric(period_begin_dt.day),
                            months=CronSingleValueNumeric(period_begin_dt.month),
                        ),
                    ),
                    "instancetype": None,
                },
                {
                    "period": RunningPeriod(
                        name=f"{name_id}-period-2",
                        begintime=parse_time_str("00:00"),
                        endtime=period_end_dt.time(),
                        cron_recurrence=CronRecurrenceExpression(
                            monthdays=CronSingleValueNumeric(period_end_dt.day),
                            months=CronSingleValueNumeric(period_end_dt.month),
                        ),
                    ),
                    "instancetype": None,
                },
            ]
        else:
            periods = [
                {
                    "period": RunningPeriod(
                        name=f"{name_id}-period-1",
                        begintime=period_begin_dt.time(),
                        endtime=parse_time_str("23:59"),
                        cron_recurrence=CronRecurrenceExpression(
                            monthdays=CronSingleValueNumeric(period_begin_dt.day),
                            months=CronSingleValueNumeric(period_begin_dt.month),
                        ),
                    ),
                    "instancetype": None,
                },
                {
                    "period": RunningPeriod(
                        name=f"{name_id}-period-2",
                        cron_recurrence=CronRecurrenceExpression(
                            monthdays=CronSingleValueNumeric(
                                (period_end_dt - timedelta(days=1)).day
                            ),
                            months=CronSingleValueNumeric(
                                (period_end_dt - timedelta(days=1)).month
                            ),
                        ),
                    ),
                    "instancetype": None,
                },
                {
                    "period": RunningPeriod(
                        name=f"{name_id}-period-3",
                        begintime=parse_time_str("00:00"),
                        endtime=period_end_dt.time(),
                        cron_recurrence=CronRecurrenceExpression(
                            monthdays=CronSingleValueNumeric(period_end_dt.day),
                            months=CronSingleValueNumeric(period_end_dt.month),
                        ),
                    ),
                    "instancetype": None,
                },
            ]

        schedule: Final = InstanceSchedule(
            name=name_id,
            timezone=self.schedule_timezone,
            description=f"{name_id} maintenance window",
            enforced=True,
            periods=periods,
        )

        return schedule

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
            next_execution_time=(
                isoparse(identity["NextExecutionTime"])
                if "NextExecutionTime" in identity
                else None
            ),
            duration_hours=identity["Duration"],
        )

    @classmethod
    def from_item(
        cls, item: dict[str, AttributeValueTypeDef]
    ) -> "EC2SSMMaintenanceWindow":
        """Return a maintenance window object from a DynamoDB `get_item` response"""
        # Like `from_identity`, this function must use `isoparse` to parse
        # `next_execution_time` because Instance Scheduler may have stored the value
        # from the service response verbatim.

        # in addition to the fields explicitly loaded here, maintenance window items
        # may have a Number attribute named TimeToLive that is not used

        # the output type of a table scan is wider than query, so more validation is
        # required
        validate_string_item(item, "account-region", True)
        validate_string_item(item, "name-id", True)
        validate_string_item(item, "ScheduleTimezone", True)
        validate_string_item(item, "NextExecutionTime", False)
        validate_number_item(item, "Duration", True)

        account_id, region = item["account-region"]["S"].split(":")
        window_name, window_id = item["name-id"]["S"].split(":")

        return EC2SSMMaintenanceWindow(
            account_id=account_id,
            region=region,
            window_id=window_id,
            window_name=window_name,
            schedule_timezone=ZoneInfo(item["ScheduleTimezone"]["S"]),
            next_execution_time=(
                isoparse(item["NextExecutionTime"]["S"])
                if "NextExecutionTime" in item
                else None
            ),
            duration_hours=int(item["Duration"]["N"]),
        )
