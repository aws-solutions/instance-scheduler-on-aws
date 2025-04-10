# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import inspect
from dataclasses import dataclass, field
from os import environ
from typing import (
    TYPE_CHECKING,
    Any,
    NotRequired,
    Optional,
    Sequence,
    TypedDict,
    TypeGuard,
)
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from instance_scheduler.configuration.instance_schedule import InstanceSchedule
from instance_scheduler.configuration.running_period_dict_element import (
    RunningPeriodDictElement,
)
from instance_scheduler.model.ddb_item_utils import (
    optionally,
    parse_bool,
    parse_str_set,
    skip_if_empty,
    skip_if_none,
)
from instance_scheduler.model.period_identifier import PeriodIdentifier
from instance_scheduler.model.store.period_definition_store import PeriodDefinitionStore
from instance_scheduler.util.validation import (
    ValidationException,
    validate_boolean,
    validate_string,
    validate_string_list,
)

if TYPE_CHECKING:
    from mypy_boto3_dynamodb.type_defs import AttributeValueTypeDef
else:
    AttributeValueTypeDef = object


class InvalidScheduleDefinition(Exception):
    pass


class ScheduleParams(TypedDict):
    name: str
    timezone: NotRequired[str]
    periods: NotRequired[str]  # comma separated list
    description: NotRequired[str]
    overwrite: NotRequired[bool]
    stop_new_instances: NotRequired[bool]
    ssm_maintenance_window: NotRequired[Sequence[str]]
    use_maintenance_window: NotRequired[bool]
    retain_running: NotRequired[bool]
    enforced: NotRequired[bool]
    hibernate: NotRequired[bool]
    override_status: NotRequired[str]
    configured_in_stack: NotRequired[str]


def validate_as_schedule_params(
    untyped_dict: dict[str, Any]
) -> TypeGuard[ScheduleParams]:
    """
    validate if an unknown dict conforms to the ScheduleParams shape

    This method will either return true (no errors) or raise a ValidationException describing why the provided dict
    does not conform to ScheduleParams
    """
    valid_keys = inspect.get_annotations(ScheduleParams).keys()
    for key in untyped_dict.keys():
        if key not in valid_keys:
            raise ValidationException(
                f"{key} is not a valid parameter, valid parameters are {valid_keys}"
            )

    validate_string(untyped_dict, "name", required=True)
    validate_string(untyped_dict, "timezone", required=False)
    validate_string(untyped_dict, "periods", required=False)
    validate_string(untyped_dict, "description", required=False)
    validate_boolean(untyped_dict, "overwrite", required=False)
    validate_boolean(untyped_dict, "stop_new_instances", required=False)
    validate_string_list(untyped_dict, "ssm_maintenance_window", required=False)
    validate_boolean(untyped_dict, "use_maintenance_windows", required=False)
    validate_boolean(untyped_dict, "retain_running", required=False)
    validate_boolean(untyped_dict, "enforced", required=False)
    validate_boolean(untyped_dict, "hibernate", required=False)
    validate_string(untyped_dict, "override_status", required=False)
    validate_string(untyped_dict, "configured_in_stack", required=False)
    return True


@dataclass
class ScheduleDefinition:
    name: str
    periods: Sequence[PeriodIdentifier] = field(default_factory=list)
    timezone: Optional[str] = None
    description: Optional[str] = None
    override_status: Optional[str] = None
    stop_new_instances: Optional[bool] = None
    ssm_maintenance_window: Optional[Sequence[str]] = None
    use_maintenance_window: Optional[bool] = None
    enforced: Optional[bool] = None
    hibernate: Optional[bool] = None
    retain_running: Optional[bool] = None
    configured_in_stack: Optional[str] = None

    def __post_init__(self) -> None:
        self.override_status = (
            self.override_status.lower() if self.override_status else None
        )
        self.validate()

    def validate(self) -> None:
        if not self.name:
            raise InvalidScheduleDefinition("Schedule name is required")

        if self.timezone:
            try:
                _ = ZoneInfo(self.timezone)
            except ZoneInfoNotFoundError:
                raise InvalidScheduleDefinition(f"Unknown timezone {self.timezone}")

        if self.override_status not in [
            None,
            "running",
            "stopped",
        ]:
            raise InvalidScheduleDefinition(
                f"Invalid override_status {self.override_status}, "
                f"valid values are running and stopped"
            )

        if not self.periods and not self.override_status:
            raise InvalidScheduleDefinition(
                "At least one period must be specified for a schedule"
            )

    def to_item(
        self,
    ) -> dict[str, AttributeValueTypeDef]:
        return {
            "type": {"S": "schedule"},
            "name": {"S": self.name},
            **skip_if_empty("periods", {"SS": self.periods}),
            **skip_if_none("timezone", {"S": self.timezone}),
            **skip_if_none("description", {"S": self.description}),
            **skip_if_none("override_status", {"S": self.override_status}),
            **skip_if_none("stop_new_instances", {"BOOL": self.stop_new_instances}),
            **skip_if_empty(
                "ssm_maintenance_window", {"SS": self.ssm_maintenance_window}
            ),
            **skip_if_none(
                "use_maintenance_window", {"BOOL": self.use_maintenance_window}
            ),
            **skip_if_none("enforced", {"BOOL": self.enforced}),
            **skip_if_none("hibernate", {"BOOL": self.hibernate}),
            **skip_if_none("retain_running", {"BOOL": self.retain_running}),
            **skip_if_none("configured_in_stack", {"S": self.configured_in_stack}),
        }  # must be handled by data store separately

    @classmethod
    def from_item(
        cls,
        item: dict[str, AttributeValueTypeDef],
    ) -> "ScheduleDefinition":
        raw_periods: set[str] = optionally(parse_str_set, item.get("periods"), set())
        return ScheduleDefinition(
            name=item["name"]["S"],
            periods=[PeriodIdentifier(pid) for pid in raw_periods],
            timezone=item.get("timezone", {}).get("S", None),
            description=item.get("description", {}).get("S", None),
            override_status=item.get("override_status", {}).get("S", None),
            stop_new_instances=optionally(
                parse_bool, item.get("stop_new_instances"), None
            ),
            ssm_maintenance_window=list(
                optionally(parse_str_set, item.get("ssm_maintenance_window"), [])
            )
            or None,
            use_maintenance_window=optionally(
                parse_bool, item.get("use_maintenance_window"), None
            ),
            enforced=optionally(parse_bool, item.get("enforced"), None),
            hibernate=optionally(parse_bool, item.get("hibernate"), None),
            retain_running=optionally(parse_bool, item.get("retain_running"), None),
            configured_in_stack=item.get("configured_in_stack", {}).get("S", None),
        )

    def to_schedule_params(self) -> ScheduleParams:
        params: ScheduleParams = {"name": self.name}
        if self.periods:
            params["periods"] = ",".join(self.periods)
        if self.timezone:
            params["timezone"] = self.timezone
        if self.description:
            params["description"] = self.description
        if self.override_status:
            params["override_status"] = self.override_status
        if self.stop_new_instances is not None:
            params["stop_new_instances"] = self.stop_new_instances
        if self.ssm_maintenance_window:
            params["ssm_maintenance_window"] = self.ssm_maintenance_window
        if self.use_maintenance_window is not None:
            params["use_maintenance_window"] = self.use_maintenance_window
        if self.enforced is not None:
            params["enforced"] = self.enforced
        if self.hibernate is not None:
            params["hibernate"] = self.hibernate
        if self.retain_running is not None:
            params["retain_running"] = self.retain_running
        if self.configured_in_stack:
            params["configured_in_stack"] = self.configured_in_stack

        return params

    @classmethod
    def from_schedule_params(cls, params: ScheduleParams) -> "ScheduleDefinition":
        return ScheduleDefinition(
            name=params["name"],
            periods=_period_ids_from_csv(params.get("periods", None)),
            timezone=params.get("timezone", None),
            description=params.get("description", None),
            override_status=params.get("override_status", None),
            stop_new_instances=params.get("stop_new_instances", None),
            ssm_maintenance_window=params.get("ssm_maintenance_window", None),
            use_maintenance_window=params.get("use_maintenance_window", None),
            enforced=params.get("enforced", None),
            hibernate=params.get("hibernate", None),
            retain_running=params.get("retain_running", None),
            configured_in_stack=params.get("configured_in_stack", None),
        )

    def to_instance_schedule(
        self,
        period_store: PeriodDefinitionStore,
    ) -> InstanceSchedule:
        fetched_periods = self.build_periods(period_store)

        return InstanceSchedule(
            name=self.name,
            periods=fetched_periods,
            timezone=self.build_timezone(),
            override_status=self.override_status,
            description=self.description,
            stop_new_instances=(
                bool(self.stop_new_instances)
                if self.stop_new_instances is not None
                else True
            ),
            ssm_maintenance_window=self.ssm_maintenance_window,
            use_maintenance_window=(
                bool(self.use_maintenance_window)
                if self.use_maintenance_window is not None
                else True
            ),
            enforced=bool(self.enforced),
            hibernate=bool(self.hibernate),
            retain_running=bool(self.retain_running),
            configured_in_stack=self.configured_in_stack,
        )

    def build_periods(
        self,
        period_store: PeriodDefinitionStore,
    ) -> list[RunningPeriodDictElement]:
        typed_periods: list[RunningPeriodDictElement] = []
        for period_id in self.periods:
            period_def = period_store.find_by_name(period_id.name)

            if not period_def:
                raise InvalidScheduleDefinition(
                    f"Unable to find period definition for {period_id.name}"
                )

            if period_id.desired_type:
                typed_periods.append(
                    RunningPeriodDictElement(
                        period=period_def.to_running_period(),
                        instancetype=period_id.desired_type,
                    )
                )
            else:
                typed_periods.append(
                    RunningPeriodDictElement(period=period_def.to_running_period())
                )
        return typed_periods

    def build_timezone(self) -> ZoneInfo:
        if self.timezone:
            return ZoneInfo(self.timezone)
        elif "DEFAULT_TIMEZONE" in environ:
            return ZoneInfo(environ["DEFAULT_TIMEZONE"])
        else:
            return ZoneInfo("UTC")


def _period_ids_from_csv(csv_str: Optional[str]) -> Sequence[PeriodIdentifier]:
    if not csv_str:
        return []
    else:
        return [PeriodIdentifier(period_name) for period_name in csv_str.split(",")]
