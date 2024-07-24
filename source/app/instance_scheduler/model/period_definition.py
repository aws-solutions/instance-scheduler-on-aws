# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import inspect
from dataclasses import dataclass
from typing import (
    TYPE_CHECKING,
    Any,
    Final,
    Iterable,
    NotRequired,
    Optional,
    TypedDict,
    TypeGuard,
)

from instance_scheduler.configuration.running_period import (
    RunningPeriod,
    RunningPeriodValidationException,
)
from instance_scheduler.configuration.time_utils import (
    TIME_FORMAT,
    is_valid_time_str,
    parse_time_str,
)
from instance_scheduler.cron.cron_recurrence_expression import CronRecurrenceExpression
from instance_scheduler.cron.parser import (
    parse_monthdays_expr,
    parse_months_expr,
    parse_weekdays_expr,
)
from instance_scheduler.model.ddb_item_utils import (
    optionally,
    parse_str,
    parse_str_set,
    skip_if_empty,
    skip_if_none,
)
from instance_scheduler.util.validation import ValidationException, validate_string

if TYPE_CHECKING:
    from mypy_boto3_dynamodb.type_defs import AttributeValueTypeDef
else:
    AttributeValueTypeDef = object


class InvalidPeriodDefinition(Exception):
    pass


class PeriodParams(TypedDict):
    """
    Dict definition of a period used for api calls and interaction
    """

    name: str
    begintime: NotRequired[str]
    endtime: NotRequired[str]
    weekdays: NotRequired[str]  # csv string
    monthdays: NotRequired[str]  # csv string
    months: NotRequired[str]  # csv string
    description: NotRequired[str]
    configured_in_stack: NotRequired[str]


def validate_as_period_params(untyped_dict: dict[str, Any]) -> TypeGuard[PeriodParams]:
    """
    validate if an unknown dict conforms to the PeriodParams shape

    This method will either return true (no errors) or raise a ValidationException describing why the provided dict
    does not conform to PeriodParams
    """
    valid_keys = inspect.get_annotations(PeriodParams).keys()
    for key in untyped_dict.keys():
        if key not in valid_keys:
            raise ValidationException(
                f"{key} is not a valid parameter, valid parameters are {valid_keys}"
            )

    validate_string(untyped_dict, "name", required=True)
    validate_string(untyped_dict, "begintime", required=False)
    validate_string(untyped_dict, "endtime", required=False)
    validate_string(untyped_dict, "description", required=False)
    validate_string(untyped_dict, "weekdays", required=False)
    validate_string(untyped_dict, "monthdays", required=False)
    validate_string(untyped_dict, "months", required=False)
    return True


@dataclass
class PeriodDefinition:
    name: str
    begintime: Optional[str] = None
    endtime: Optional[str] = None
    weekdays: Optional[set[str]] = None
    months: Optional[set[str]] = None
    monthdays: Optional[set[str]] = None
    description: Optional[str] = None
    configured_in_stack: Optional[str] = None

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        # will throw validation exceptions
        if not self.name:
            raise InvalidPeriodDefinition("Period name is required")

        if self.begintime and not is_valid_time_str(self.begintime):
            raise InvalidPeriodDefinition(
                f'Invalid begintime "{self.begintime}". must match the format {TIME_FORMAT}'
            )

        if self.endtime and not is_valid_time_str(self.endtime):
            raise InvalidPeriodDefinition(
                f'Invalid endtime "{self.endtime}". must match the format {TIME_FORMAT}'
            )

        cron_fields: Final = (
            self.begintime,
            self.endtime,
            self.weekdays,
            self.months,
            self.monthdays,
        )
        # must specify at least one
        if not any(field is not None for field in cron_fields):
            raise InvalidPeriodDefinition(
                "Must contain at least one of begintime, endtime, weekdays, months, monthdays"
            )

        try:
            self.to_running_period()
        except RunningPeriodValidationException as e:
            raise InvalidPeriodDefinition(e)
        except ValueError as ve:
            raise InvalidPeriodDefinition(ve)

    def to_running_period(self) -> RunningPeriod:
        return RunningPeriod(
            name=self.name,
            begintime=optionally(parse_time_str, self.begintime, None),
            endtime=optionally(parse_time_str, self.endtime, None),
            cron_recurrence=CronRecurrenceExpression(
                weekdays=parse_weekdays_expr(self.weekdays),
                monthdays=parse_monthdays_expr(self.monthdays),
                months=parse_months_expr(self.months),
            ),
        )

    def to_item(self) -> dict[str, AttributeValueTypeDef]:
        """Return this object as a dict suitable for a call to DynamoDB `put_item`"""
        return {
            "type": {"S": "period"},
            "name": {"S": self.name},
            **skip_if_none("begintime", {"S": self.begintime}),
            **skip_if_none("endtime", {"S": self.endtime}),
            **skip_if_empty("weekdays", {"SS": _optional_list(self.weekdays)}),
            **skip_if_empty("monthdays", {"SS": _optional_list(self.monthdays)}),
            **skip_if_empty("months", {"SS": _optional_list(self.months)}),
            **skip_if_none("description", {"S": self.description}),
            **skip_if_none("configured_in_stack", {"S": self.configured_in_stack}),
        }

    @classmethod
    def from_item(cls, item: dict[str, AttributeValueTypeDef]) -> "PeriodDefinition":
        return PeriodDefinition(
            name=parse_str(item["name"]),
            begintime=optionally(parse_str, item.get("begintime"), None),
            endtime=optionally(parse_str, item.get("endtime"), None),
            weekdays=optionally(parse_str_set, item.get("weekdays"), None),
            months=optionally(parse_str_set, item.get("months"), None),
            monthdays=optionally(parse_str_set, item.get("monthdays"), None),
            description=optionally(parse_str, item.get("description"), None),
            configured_in_stack=optionally(
                parse_str, item.get("configured_in_stack"), None
            ),
        )

    def to_period_params(self) -> PeriodParams:
        params: PeriodParams = {"name": self.name}
        if self.begintime:
            params["begintime"] = self.begintime
        if self.endtime:
            params["endtime"] = self.endtime
        if self.weekdays:
            params["weekdays"] = ",".join(self.weekdays)
        if self.monthdays:
            params["monthdays"] = ",".join(self.monthdays)
        if self.months:
            params["months"] = ",".join(self.months)
        if self.description:
            params["description"] = self.description
        if self.configured_in_stack:
            params["configured_in_stack"] = self.configured_in_stack

        return params

    @classmethod
    def from_period_params(cls, params: PeriodParams) -> "PeriodDefinition":
        """
        convert PeriodParams to a RunningPeriodDefinition

        This method may raise InvalidPeriodDefinition if RunningPeriod invariants are violated
        """
        return PeriodDefinition(
            name=params["name"],
            begintime=params.get("begintime", None),
            endtime=params.get("endtime", None),
            weekdays=optionally(parse_csv_as_set, params.get("weekdays"), None),
            months=optionally(parse_csv_as_set, params.get("months"), None),
            monthdays=optionally(parse_csv_as_set, params.get("monthdays"), None),
            description=params.get("description", None),
            configured_in_stack=params.get("configured_in_stack", None),
        )


def _optional_list(input: Optional[Iterable[str]]) -> Optional[list[str]]:
    if input is None:
        return None
    return list(input)


def parse_csv_as_set(value: str) -> set[str]:
    return {token.strip() for token in value.split(",")}
