# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import dataclasses
import json
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Callable, TypeGuard, cast
from zoneinfo import ZoneInfo

from packaging.version import Version

from instance_scheduler import __version__
from instance_scheduler.handler.base import MainHandler
from instance_scheduler.handler.cli.schedule_usage import get_schedule_usage
from instance_scheduler.handler.environments.main_lambda_environment import (
    MainLambdaEnv,
)
from instance_scheduler.model.ddb_item_utils import optionally
from instance_scheduler.model.period_definition import (
    PeriodDefinition,
    validate_as_period_params,
)
from instance_scheduler.model.schedule_definition import (
    ScheduleDefinition,
    validate_as_schedule_params,
)
from instance_scheduler.model.store.dynamo_period_definition_store import (
    DynamoPeriodDefinitionStore,
)
from instance_scheduler.model.store.dynamo_schedule_definition_store import (
    DynamoScheduleDefinitionStore,
)
from instance_scheduler.model.store.period_definition_store import (
    PeriodAlreadyExistsException,
    PeriodDefinitionStore,
    UnknownPeriodException,
)
from instance_scheduler.model.store.schedule_definition_store import (
    ScheduleAlreadyExistsException,
    UnknownScheduleException,
)
from instance_scheduler.ops_metrics.metric_type.cli_request_metric import (
    CliRequestMetric,
)
from instance_scheduler.ops_metrics.metrics import collect_metric
from instance_scheduler.util import safe_json
from instance_scheduler.util.logger import Logger
from instance_scheduler.util.validation import ValidationException, validate_string

if TYPE_CHECKING:
    from aws_lambda_powertools.utilities.typing import LambdaContext
else:
    LambdaContext = object

CURRENT_CLI_VERSION = __version__
MINIMUM_SUPPORTED_CLI_VERSION = "3.0.0"

CLI_SOURCE = "scheduler.cli"

LOG_STREAM = "{}-{:0>4d}{:0>2d}{:0>2d}"

AdminCliRequest = dict[str, Any]


class PeriodInUseException(Exception):
    pass


class ManagedByCfnException(Exception):
    pass


class UnsupportedVersionException(Exception):
    pass


class CliRequestHandler(MainHandler[AdminCliRequest]):
    """
    Class to handles requests from admin CLI
    """

    def __init__(
        self, event: AdminCliRequest, context: LambdaContext, env: MainLambdaEnv
    ) -> None:
        """
        Initializes handle instance
        :param event: event to handle
        :param context: lambda context
        """
        self._event = event
        self._context = context
        self._schedule_store = DynamoScheduleDefinitionStore(env.config_table_name)
        self._period_store = DynamoPeriodDefinitionStore(env.config_table_name)

        # Setup logging
        classname = self.__class__.__name__
        dt = datetime.now(timezone.utc)
        log_stream = LOG_STREAM.format(classname, dt.year, dt.month, dt.day)
        self._logger = Logger(
            log_group=env.log_group,
            log_stream=log_stream,
            topic_arn=env.topic_arn,
            debug=env.enable_debug_logging,
        )

    @property
    def action(self) -> Any:
        """
        Retrieves admin REST api action from the event
        :return: name of the action of the event
        """
        return self._event["action"]

    @property
    def parameters(self) -> dict[Any, Any]:
        params = self._event.get("parameters", {})
        return {p.replace("-", "_"): params[p] for p in params}

    @property
    def version(self) -> Any:
        return self._event["version"]

    @staticmethod
    def is_handling_request(event: Mapping[str, Any]) -> TypeGuard[AdminCliRequest]:
        """
        Returns True if the handler can handle the event
        :param event: tested event
        :return: True if the handles does handle the tested event
        """

        if event.get("source", "") != CLI_SOURCE:
            return False
        return "action" in event

    def handle_request(self) -> Any:
        """
        Handles the event
        :return: result of handling the event, result send back to REST admin api
        """

        def snake_to_pascal_case(s: Any) -> Any:
            converted = ""
            s = s.strip("_").capitalize()
            i = 0

            while i < len(s):
                if s[i] == "_":
                    i += 1
                    converted += s[i].upper()
                else:
                    converted += s[i]
                i += 1

            return converted

        def dict_to_pascal_case(d: Any) -> Any:
            d_result = {}

            if isinstance(d, dict):
                for i in d:
                    key = snake_to_pascal_case(i)
                    d_result[key] = dict_to_pascal_case(d[i])
                return d_result

            elif isinstance(d, list):
                return [dict_to_pascal_case(item) for item in d]

            return d

        try:
            self._logger.info(
                "Handler {} : Received CLI request {}",
                self.__class__.__name__,
                json.dumps(self._event),
            )

            # Supports cli versions from some minimum version to current solution minor version
            solution_version = Version(self.version)
            cli_version = Version(CURRENT_CLI_VERSION)
            if (
                not Version(MINIMUM_SUPPORTED_CLI_VERSION) <= solution_version
                or solution_version.major != cli_version.major
                or solution_version.minor != cli_version.minor
            ):

                raise UnsupportedVersionException(
                    f"CLI version {self.version} is not supported for this version of the solution. Please update to a supported version ({get_supported_cli_versions()})."
                )

            collect_metric(
                CliRequestMetric(command_used=self.action), logger=self._logger
            )

            api_result = self.handle_command(self.action, self.parameters)

            # convert to awscli PascalCase output format
            result = dict_to_pascal_case(api_result)

            # log formatted result
            json_result = safe_json(result, 3)
            self._logger.info("Call result is {}", json_result)

            return json.loads(
                json_result
            )  # returned as dict to allow lambda to control final format

        except Exception as ex:
            self._logger.info("Call failed, error is {}", str(ex))
            return {"Error": str(ex)}
        finally:
            self._logger.flush()

    def handle_command(self, command: str, parameters: dict[str, Any]) -> Any:
        commands: dict[str, Callable[[dict[str, Any]], Any]] = {
            "create-period": self.create_period_cmd,
            "create-schedule": self.create_schedule_cmd,
            "delete-period": self.delete_period_cmd,
            "delete-schedule": self.delete_schedule_cmd,
            "describe-periods": self.describe_periods_command,
            "describe-schedules": self.describe_schedules_command,
            "update-period": self.update_period_cmd,
            "update-schedule": self.update_schedule_cmd,
            "describe-schedule-usage": self.describe_schedule_usage_command,
        }

        command_func = commands.get(command)
        if command_func:
            return command_func(parameters)
        else:
            raise ValueError(f"Command {command} does not exist")

    def create_period_cmd(self, parameters: dict[str, Any]) -> Any:
        if validate_as_period_params(parameters):
            period_def = PeriodDefinition.from_period_params(parameters)
            try:
                self._period_store.put(period_def, overwrite=False)
                return {
                    "period": {
                        "type": "period",
                        **_strip_none_values(dataclasses.asdict(period_def)),
                    }
                }
            except PeriodAlreadyExistsException as e:
                raise PeriodAlreadyExistsException(f"error: {e}")

    def create_schedule_cmd(self, parameters: dict[str, Any]) -> Any:
        if validate_as_schedule_params(parameters):
            schedule_def = ScheduleDefinition.from_schedule_params(parameters)
            validate_periods_exist(schedule_def, self._period_store)
            try:
                self._schedule_store.put(schedule_def, overwrite=False)
                return {
                    "schedule": {
                        "type": "schedule",
                        **_strip_none_values(dataclasses.asdict(schedule_def)),
                    }
                }
            except ScheduleAlreadyExistsException as e:
                raise ScheduleAlreadyExistsException(f"error: {e}")

    def delete_period_cmd(self, parameters: dict[str, Any]) -> Any:
        if validate_string(parameters, "name", required=True):
            period_name: str = parameters["name"]
            existing_period = self._period_store.find_by_name(period_name)
            if not existing_period:
                raise UnknownPeriodException(
                    f"not found: period {period_name} does not exist"
                )

            if is_managed_by_cfn(existing_period):
                raise ManagedByCfnException(
                    f"Period {existing_period.name} is owned by {existing_period.configured_in_stack} and cannot be"
                    f" deleted by the cli. Please delete the owning stack to delete this period"
                )

            schedules_using_period = self._schedule_store.find_by_period(period_name)
            if schedules_using_period:
                raise PeriodInUseException(
                    f"error: period {period_name} can not be deleted "
                    f"because it is still used in schedule(s) "
                    f"{[sched.name for sched in schedules_using_period.values()]}"
                )

            self._period_store.delete(period_name)
            return {"period": period_name}

    def delete_schedule_cmd(self, parameters: dict[str, Any]) -> Any:
        if validate_string(parameters, "name", required=True):
            schedule_name: str = parameters["name"]
            existing_schedule = self._schedule_store.find_by_name(schedule_name)
            if not existing_schedule:
                raise UnknownScheduleException(
                    f"not found: schedule {schedule_name} does not exist"
                )

            if is_managed_by_cfn(existing_schedule):
                raise ManagedByCfnException(
                    f"Schedule {existing_schedule.name} is owned by {existing_schedule.configured_in_stack} and cannot be"
                    f" deleted by the cli. Please delete the owning stack to delete this schedule"
                )

            self._schedule_store.delete(schedule_name)
            return {"schedule": schedule_name}

    def update_period_cmd(self, parameters: dict[str, Any]) -> Any:
        if validate_as_period_params(parameters):
            period_def = PeriodDefinition.from_period_params(parameters)
            old_period_def = self._period_store.find_by_name(period_def.name)
            if not old_period_def:
                raise UnknownPeriodException(
                    f"not found: period {period_def.name} does not exist"
                )
            if is_managed_by_cfn(old_period_def):
                raise ManagedByCfnException(
                    f"Period {old_period_def.name} is owned by {old_period_def.configured_in_stack} and cannot be"
                    f" edited by the cli. Please update the owning stack to edit this period"
                )
            self._period_store.put(period_def, overwrite=True)
            return {
                "period": {
                    "type": "period",
                    **_strip_none_values(dataclasses.asdict(period_def)),
                }
            }

    def update_schedule_cmd(self, parameters: dict[str, Any]) -> Any:
        if validate_as_schedule_params(parameters):
            schedule_def = ScheduleDefinition.from_schedule_params(parameters)
            validate_periods_exist(schedule_def, self._period_store)

            old_schedule_def = self._schedule_store.find_by_name(schedule_def.name)
            if not old_schedule_def:
                raise UnknownScheduleException(
                    f"not found: schedule {schedule_def.name} does not exist"
                )
            if is_managed_by_cfn(old_schedule_def):
                raise ManagedByCfnException(
                    f"Schedule {old_schedule_def.name} is owned by {old_schedule_def.configured_in_stack} and cannot be"
                    f" edited by the cli. Please update the owning stack to edit this schedule"
                )
            self._schedule_store.put(schedule_def, overwrite=True)
            return {
                "schedule": {
                    "type": "schedule",
                    **_strip_none_values(dataclasses.asdict(schedule_def)),
                }
            }

    def describe_periods_command(self, parameters: dict[str, Any]) -> Any:
        validate_string(parameters, "name", required=False)
        name = parameters.get("name", None)

        if name:
            period_def = self._period_store.find_by_name(name)
            if not period_def:
                raise UnknownPeriodException(f"not found: period {name} does not exist")
            return {
                "periods": [
                    {
                        "type": "period",
                        **_strip_none_values(dataclasses.asdict(period_def)),
                    }
                ]
            }
        else:
            period_defs = self._period_store.find_all()
            return {
                "periods": [
                    {
                        "type": "period",
                        **_strip_none_values(dataclasses.asdict(period_def)),
                    }
                    for period_def in period_defs.values()
                ]
            }

    def describe_schedules_command(self, parameters: dict[str, Any]) -> Any:
        validate_string(parameters, "name", required=False)
        name = parameters.get("name", None)

        if name:
            schedule_def = self._schedule_store.find_by_name(name)
            if not schedule_def:
                raise UnknownScheduleException(
                    f"not found: schedule {name} does not exist"
                )
            return {
                "schedules": [
                    {
                        "type": "schedule",
                        **_strip_none_values(dataclasses.asdict(schedule_def)),
                    }
                ]
            }
        else:
            schedule_defs = self._schedule_store.find_all()
            return {
                "schedules": [
                    {
                        "type": "schedule",
                        **_strip_none_values(dataclasses.asdict(schedule_def)),
                    }
                    for schedule_def in schedule_defs.values()
                ]
            }

    def describe_schedule_usage_command(self, parameters: dict[str, Any]) -> Any:
        validate_string(parameters, "name", required=True)
        validate_string(parameters, "startdate", required=False)
        validate_string(parameters, "enddate", required=False)

        name: str = cast(str, parameters.get("name"))

        schedule = self._schedule_store.find_by_name(name)
        if schedule is None:
            raise ValueError(f"not found: schedule {name} does not exist")
        try:
            start_date = optionally(_parse_date, parameters.get("startdate"), None)
        except ValueError as e:
            raise ValueError(
                f"error: invalid startdate {parameters.get('startdate')}, {e}"
            )
        try:
            end_date = optionally(_parse_date, parameters.get("enddate"), None)
        except ValueError as e:
            raise ValueError(f"error: invalid enddate {parameters.get('enddate')}, {e}")

        # name, start_date, and end_date parsed
        tz = ZoneInfo(schedule.timezone) if schedule.timezone else timezone.utc
        start_date = start_date.replace(tzinfo=tz) if start_date else None
        end_date = end_date.replace(tzinfo=tz) if end_date else None
        return get_schedule_usage(
            schedule.to_instance_schedule(self._period_store),
            start_date,
            end_date,
        )


def _strip_none_values(dict_to_strip: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in dict_to_strip.items() if v is not None}


def _parse_date(date_str: str) -> datetime:
    try:
        return datetime.strptime(date_str, "%Y%m%d")
    except ValueError as ex:
        raise ValueError(f"must be a valid date in format yyyymmdd {str(ex)}")


def validate_periods_exist(
    schedule_def: ScheduleDefinition, period_store: PeriodDefinitionStore
) -> bool:
    # validate all periods exist -- carrying forward validation behavior that existed in 1.5.1
    for period_id in schedule_def.periods:
        period = period_store.find_by_name(period_id.name)
        if not period:
            raise ValidationException(
                f"error: not found: period {period_id.name} does not exist"
            )
    return True


def is_managed_by_cfn(resource: PeriodDefinition | ScheduleDefinition) -> bool:
    return resource.configured_in_stack is not None


def get_supported_cli_versions() -> str:
    return (
        CURRENT_CLI_VERSION
        if CURRENT_CLI_VERSION == MINIMUM_SUPPORTED_CLI_VERSION
        else f"{MINIMUM_SUPPORTED_CLI_VERSION}-{CURRENT_CLI_VERSION}"
    )
