# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import json
import re
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Literal, Optional, TypedDict, TypeVar
from zoneinfo import ZoneInfo

from boto3.dynamodb.conditions import Key

from instance_scheduler import ScheduleState, configuration
from instance_scheduler.configuration.config_dynamodb_adapter import (
    ConfigDynamodbAdapter,
)
from instance_scheduler.configuration.instance_schedule import Instance
from instance_scheduler.configuration.scheduler_config import GlobalConfig
from instance_scheduler.configuration.scheduler_config_builder import (
    SchedulerConfigBuilder,
)
from instance_scheduler.configuration.setbuilders.month_setbuilder import (
    MonthSetBuilder,
)
from instance_scheduler.configuration.setbuilders.monthday_setbuilder import (
    MonthdaySetBuilder,
)
from instance_scheduler.configuration.setbuilders.weekday_setbuilder import (
    WeekdaySetBuilder,
)
from instance_scheduler.util.app_env import get_app_env
from instance_scheduler.util.dynamodb_utils import DynamoDBUtils
from instance_scheduler.util.logger import Logger

if TYPE_CHECKING:
    from aws_lambda_powertools.utilities.typing import LambdaContext

    T = TypeVar("T")
else:
    LambdaContext = object
    T = object

ERR_PERIOD_BEGIN_LATER_THAN_END = (
    "error: period begintime {} can not be later than endtime {}"
)
ERR_SCHEDULE_INVALID_OVERRIDE = "{} is not a valid value for {}, possible values are {}"
ERR_SCHEDULE_OVERWRITE_OVERRIDE_EXCLUSIVE = (
    "{} option is mutually exclusive with {} option"
)
ERR_CREATE_PERIOD_EXISTS = "error: period {} already exists"
ERR_CREATE_SCHEDULE_EXISTS = "error: schedule {} already exists"
ERR_DEL_PERIOD_IN_USE = (
    "error: period {} can not be deleted because it is still used in schedule(s) {}"
)
ERR_PERIOD_NOT_FOUND = "not found: period {} does not exist"
ERR_DEL_SCHEDULE_NAME_EMPTY = "error: schedule name parameter can not be empty"
ERR_SCHEDULE_NOT_FOUND = "not found: schedule {} does not exist"
ERR_EMPTY_PERIOD_NAME = "error: period name parameter can not be empty"
ERR_GET_SCHEDULE_NAME_EMPTY = "error: error schedule name parameter can not be empty"
ERR_GET_USAGE_INVALID_END_DATE = (
    "error: invalid enddate {}, must be a valid date in format yyyymmdd {}"
)
ERR_GET_USAGE_INVALID_START_DATE = (
    "error: invalid startdate {}, must be a valid date in format yyyymmdd {}"
)
ERR_GET_USAGE_SCHEDULE_NAME_EMPTY = (
    "error: error schedule name parameter can not be empty"
)
ERR_GET_USAGE_START_MUST_BE_LESS_OR_EQUAL_STOP = (
    "stop_date must be equal or later than start_date"
)
ERR_NAME_PARAM_MISSING = "error: name parameter is missing"
ERR_NO_PERIODS = "error: at least one period condition must be specified"
ERR_PERIOD_INVALID_MONTHDAYS = "error: {} is not a valid month days specification"
ERR_PERIOD_INVALID_MONTHS = "error: {} is not a valid months specification"
ERR_PERIOD_INVALID_TIME = "error: {} {} is not a valid time"
ERR_PERIOD_INVALID_WEEKDAYS = "error: {} is not a valid weekdays specification {}"
ERR_PERIOD_UNKNOWN_PARAMETER = (
    "error: {} is not a valid parameter, valid parameters are {}"
)
ERR_SCHEDULE_INVALID_BOOLEAN = "error: {} for parameter {} is not a valid boolean value"
ERR_SCHEDULE_INVALID_TIMEZONE = "error: {} is not a valid time zone for parameter {}"
ERR_SCHEDULE_NAME_MISSING = "error: name parameter is missing"
ERR_SCHEDULE_NO_PERIOD = "error: at least one period must be specified for a schedule"
ERR_SCHEDULE_PERIOD_DOES_NOT_EXISTS = "error: not found: period {} does not exist"
ERR_SCHEDULE_UNKNOWN_PARAMETER = (
    "error: {} is not a valid parameter, valid parameters are {}"
)
ERR_UPDATE_INVALID_BOOL_PARAM = (
    "error: {} for parameter {} is not a valid boolean value"
)
ERR_UPDATE_INVALID_TZ_PARAMETER = "error: {} is not a valid time zone for parameter {}"
ERR_UPDATE_SCHEDULE_NAME_EMPTY = "error: schedule name parameter can not be empty"
ERR_UPDATE_TAGNAME_EMPTY = "error: tagname parameter must be specified"
ERR_UPDATE_UNKNOWN_PARAMETER = "error: {} is not a valid parameter"
ERR_UPDATE_UNKNOWN_SERVICE = "{} is not a supported service"
ERR_STOP_MUST_BE_LATER_OR_EQUAL_TO_START = (
    "stop_date must be equal or later than start_date"
)

INF_ADD_ACCOUNT_EVENT_PERMISSION = (
    "Add permission for account {} to put events on message bus, sid is {}"
)
INF_REMOVE_EVENT_PERMISSION = (
    "Remove permission for account {} to put events on event bus, sid = {}"
)

ConfigTableConfigItemType = Literal["config"]
ConfigTableScheduleItemType = Literal["schedule"]
ConfigTablePeriodItemType = Literal["period"]

ConfigTableItemType = (
    ConfigTableConfigItemType | ConfigTableScheduleItemType | ConfigTablePeriodItemType
)


class ConfigTableItem(TypedDict, total=False):
    type: ConfigTableItemType
    name: str


class ConfigTableConfigItem(ConfigTableItem):
    use_metrics: bool
    remote_account_ids: set[str]
    organization_id: str
    scheduler_role_name: str
    namespace: str
    aws_partition: str
    default_timezone: str
    regions: set[str] | list[str]
    schedule_lambda_account: bool
    tagname: str
    trace: bool
    enable_ssm_maintenance_windows: bool
    scheduled_services: set[str]
    schedule_clusters: bool
    create_rds_snapshot: bool
    started_tags: str
    stopped_tags: str


OverrideStatusRunning = Literal["running"]
OverrideStatusStopped = Literal["stopped"]

OverrideStatus = OverrideStatusRunning | OverrideStatusStopped


class ConfigTableScheduleItem(ConfigTableItem, total=False):
    timezone: str
    periods: set[str]
    description: str
    overwrite: bool
    use_metrics: bool
    stop_new_instances: bool
    use_maintenance_window: bool
    ssm_maintenance_window: str
    retain_running: bool
    enforced: bool
    hibernate: bool
    override_status: OverrideStatus
    configured_in_stack: str


class ConfigTablePeriodItem(ConfigTableItem, total=False):
    begintime: str
    endtime: str
    weekdays: set[str]
    monthdays: set[str]
    months: set[str]
    description: str


class ConfigAdmin:
    """
    Implements admin api for Scheduler
    """

    TYPE_ATTR = "type"
    # regex for checking time formats H:MM and HH:MM
    TIME_REGEX = "^([0|1]?[0-9]|2[0-3]):[0-5][0-9]$"

    SUPPORTED_SERVICES = ["ec2", "rds"]

    class CustomEncoder(json.JSONEncoder):
        """
        Custom encoding to handle unsupported data types
        """

        def default(self, o: Any) -> Any:
            if isinstance(o, set):
                return list(o)
            if isinstance(o, datetime):
                return o.replace(second=0).strftime("%x %X")

            return json.JSONEncoder.default(self, o)

    def __init__(
        self, logger: Optional[Logger], context: Optional[LambdaContext]
    ) -> None:
        """
        Initializes the config API
        :param logger: logger for the admin api
        :param context: Lambda context
        """
        self._table_name = self.table_name
        self._table: Any = DynamoDBUtils.get_dynamodb_table_resource_ref(
            self._table_name
        )
        self._configuration: Optional[GlobalConfig] = None
        self._logger = logger
        self._context = context

    @property
    def configuration(self) -> GlobalConfig:
        """
        Returns and cached configuration
        :return: scheduler configuration
        """
        if self._configuration is None:
            configdata = ConfigDynamodbAdapter(self._table.name).config
            self._configuration = SchedulerConfigBuilder(logger=self._logger).build(
                configdata
            )
        return self._configuration

    @property
    def table_name(self) -> str:
        return get_app_env().config_table_name

    def update_config(self, settings: ConfigTableConfigItem) -> Any:
        """
        Updates configuration, validates new values
        :param settings: settings values
        :return: updated values
        """
        valid_attributes = [
            configuration.METRICS,
            configuration.REMOTE_ACCOUNT_IDS,
            configuration.ORGANIZATION_ID,
            configuration.SCHEDULER_ROLE_NAME,
            configuration.NAMESPACE,
            configuration.AWS_PARTITION,
            configuration.DEFAULT_TIMEZONE,
            configuration.REGIONS,
            configuration.SCHEDULE_LAMBDA_ACCOUNT,
            configuration.TAGNAME,
            configuration.TRACE,
            configuration.ENABLE_SSM_MAINTENANCE_WINDOWS,
            ConfigAdmin.TYPE_ATTR,
            configuration.SCHEDULED_SERVICES,
            configuration.SCHEDULE_CLUSTERS,
            configuration.CREATE_RDS_SNAPSHOT,
            configuration.STARTED_TAGS,
            configuration.STOPPED_TAGS,
        ]

        checked_settings: dict[str, str | bool | set[str]] = {}

        for attr in settings:
            if attr in [ConfigAdmin.TYPE_ATTR, configuration.NAME]:
                continue

            # only valid fields
            if attr not in valid_attributes:
                raise ValueError(ERR_UPDATE_UNKNOWN_PARAMETER.format(attr))

            # remove None fields
            if settings[attr] is None:  # type: ignore[literal-required]
                continue

            # remove empty strings
            if len(str(settings[attr])) == 0:  # type: ignore[literal-required]
                continue

            # make sure these fields are set as sets
            if attr in [
                configuration.REGIONS,
                configuration.REMOTE_ACCOUNT_IDS,
                configuration.SCHEDULED_SERVICES,
            ]:
                temp = self._ensure_set(settings[attr])  # type: ignore[literal-required]
                if len(settings[attr]) > 0:  # type: ignore[literal-required]
                    checked_settings[attr] = temp

                continue

            # make sure these fields are valid booleans
            if attr in [
                configuration.METRICS,
                configuration.TRACE,
                configuration.ENABLE_SSM_MAINTENANCE_WINDOWS,
                configuration.SCHEDULE_LAMBDA_ACCOUNT,
                configuration.CREATE_RDS_SNAPSHOT,
                configuration.SCHEDULE_CLUSTERS,
            ]:
                bool_value = self._ensure_bool(settings[attr])  # type: ignore[literal-required]
                if bool_value is None:
                    raise ValueError(
                        ERR_UPDATE_INVALID_BOOL_PARAM.format(settings[attr], attr)  # type: ignore[literal-required]
                    )
                checked_settings[attr] = bool_value
                continue

            # validate timezone
            if attr == configuration.DEFAULT_TIMEZONE:
                default_tz = settings[configuration.DEFAULT_TIMEZONE]  # type: ignore[literal-required]
                if not SchedulerConfigBuilder.is_valid_timezone(default_tz):
                    raise ValueError(
                        ERR_UPDATE_INVALID_TZ_PARAMETER.format(
                            default_tz, configuration.DEFAULT_TIMEZONE
                        )
                    )
                checked_settings[attr] = default_tz
                continue

            checked_settings[attr] = settings[attr]  # type: ignore[literal-required]

            if configuration.TAGNAME not in settings:
                raise ValueError(ERR_UPDATE_TAGNAME_EMPTY)

            for service in settings.get("scheduled_services", []):
                if service not in ConfigAdmin.SUPPORTED_SERVICES:
                    raise ValueError(ERR_UPDATE_UNKNOWN_SERVICE.format(service))

        # keys for config item
        checked_settings[ConfigAdmin.TYPE_ATTR] = "config"
        checked_settings[configuration.NAME] = "scheduler"

        self._table.put_item(Item=checked_settings)

        return ConfigAdmin._for_output(checked_settings)

    def list_periods(self) -> dict[Literal["periods"], Any]:
        """
        Lists all periods
        :return: all configured periods
        """
        periods = self._list_periods()
        for period in periods:
            ConfigAdmin._for_output(period)
        return {"periods": ConfigAdmin._for_output(periods)}

    def get_period(
        self, name: str, exception_if_not_exists: bool = True
    ) -> Optional[dict[Literal["period"], Any]]:
        """
        Gets a specific period
        :param name: name of the period
        :param exception_if_not_exists: set to True to raise an exception if it does not exist
        :return:
        """
        if name is None or len(name) == 0:
            raise ValueError(ERR_EMPTY_PERIOD_NAME)
        period = self._get_period(name)
        if period is None:
            if exception_if_not_exists:
                raise ValueError(ERR_PERIOD_NOT_FOUND.format(name))
            return None
        return {"period": ConfigAdmin._for_output(period)}

    def create_period(self, kwargs: ConfigTablePeriodItem) -> dict[str, Any]:
        """
        Creates a new period
        :param kwargs: period parameters, see validate_period for allowed parameters
        :return: Validated and created period
        """
        period = self._validate_period(kwargs)
        name = period["name"]
        if self._get_period(name) is not None:
            raise ValueError(ERR_CREATE_PERIOD_EXISTS.format(name))
        self._table.put_item(Item=period)
        return {"period": ConfigAdmin._for_output(period)}

    def update_period(self, kwargs: ConfigTablePeriodItem) -> dict[str, Any]:
        """
        Updates an existing period
        :param kwargs:  period data, see validate_period for allowed parameters
        :return: validated and updated period
        """
        period = self._validate_period(kwargs)
        name = period["name"]
        if name is None or len(name) == 0:
            raise ValueError(ERR_EMPTY_PERIOD_NAME)
        if self._get_period(name) is None:
            raise ValueError(ERR_PERIOD_NOT_FOUND.format(name))
        self._table.put_item(Item=period)
        return {"period": ConfigAdmin._for_output(period)}

    def delete_period(
        self, name: str, exception_if_not_exists: bool = False
    ) -> Optional[dict[Literal["period"], str]]:
        """
        Deletes a period. Note that a period can ony be deleted when not longer used in any schedule
        :param name: Name of the period
        :param exception_if_not_exists: Set to true is an exception should be raised if the period did not exist
        :return:
        """
        if name is None or len(name) == 0:
            raise ValueError(ERR_EMPTY_PERIOD_NAME)

        # test if period is used in any schedule
        schedules_using_period = []
        for s in self._list_schedules():
            for p in s.get(configuration.PERIODS, []):
                # period can be a combination of name and instance type
                if p.split(configuration.INSTANCE_TYPE_SEP)[0] == name:
                    schedules_using_period.append(s[configuration.NAME])

        if len(schedules_using_period) > 0:
            raise ValueError(
                ERR_DEL_PERIOD_IN_USE.format(name, ", ".join(schedules_using_period))
            )

        if self._get_period(name) is not None:
            self._table.delete_item(Key={"name": name, "type": "period"})
            return {"period": name}
        else:
            if exception_if_not_exists:
                raise ValueError(ERR_PERIOD_NOT_FOUND.format(name))
            return None

    def list_schedules(self) -> dict[Literal["schedules"], Any]:
        """
        List all configured schedules
        :return: all schedules
        """
        schedules = self._list_schedules()
        return {"schedules": ConfigAdmin._for_output(schedules)}

    def get_schedule(
        self, name: str, exception_if_not_exists: bool = True
    ) -> Optional[dict[Literal["schedule"], Any]]:
        """
        Gets the information for a specific schedule
        :param name: name of the schedule
        :param exception_if_not_exists: set to True if an exception should be raised if the schedule does not exist
        :return: schedule data, Non if schedule does not exists and exception_if_not_exists is set to False
        """
        if name is None or len(name) == 0:
            raise ValueError(ERR_GET_SCHEDULE_NAME_EMPTY)
        schedule = self._get_schedule(name)
        if schedule is None:
            if exception_if_not_exists:
                raise ValueError(ERR_SCHEDULE_NOT_FOUND.format(name))
            return None
        return {"schedule": ConfigAdmin._for_output(schedule)}

    def create_schedule(
        self, kwargs: ConfigTableScheduleItem
    ) -> dict[Literal["schedule"], Any]:
        """
        Creates a new schedule
        :param kwargs: schedule data, see validate_schedule for allowed parameters
        :return: Validated data of created schedule
        """
        schedule = self._validate_schedule(kwargs)
        name = schedule["name"]
        if self._get_schedule(name) is not None:
            raise ValueError(ERR_CREATE_SCHEDULE_EXISTS.format(name))
        self._table.put_item(Item=schedule)
        return {"schedule": ConfigAdmin._for_output(schedule)}

    def update_schedule(
        self, kwargs: ConfigTableScheduleItem
    ) -> dict[Literal["schedule"], Any]:
        """
        Updates an existing schedule
        :param kwargs: schedule data, see validate_schedule for allowed parameters
        :return: Validated updated schedule
        """
        schedule = self._validate_schedule(kwargs)
        name = schedule["name"]
        if name is None or len(name) == 0:
            raise ValueError(ERR_UPDATE_SCHEDULE_NAME_EMPTY)
        if self._get_schedule(name) is None:
            raise ValueError(ERR_SCHEDULE_NOT_FOUND.format(name))
        self._table.put_item(Item=schedule)
        return {"schedule": ConfigAdmin._for_output(schedule)}

    def delete_schedule(
        self, name: str, exception_if_not_exists: bool = True
    ) -> Optional[dict[Literal["schedule"], str]]:
        """
        Deletes a schedule
        :param name: name of the schedule
        :param exception_if_not_exists: True if an exception should be raised if the schedule does not exists
        :return: Deleted schedule, None if it did not exist
        """
        if name is None or len(name) == 0:
            raise ValueError(ERR_DEL_SCHEDULE_NAME_EMPTY)
        if self._get_schedule(name) is None:
            if exception_if_not_exists:
                raise ValueError(ERR_SCHEDULE_NOT_FOUND.format(name))
            return None
        self._table.delete_item(Key={"name": name, "type": "schedule"})
        return {"schedule": name}

    def get_schedule_usage(
        self,
        name: str,
        startdate: Optional[datetime] = None,
        enddate: Optional[datetime] = None,
    ) -> Any:
        """
        Get running periods for a schedule in a period
        :param name: name of the schedule
        :param startdate: start date of the period, None is today
        :param enddate: end date of the period, None is today
        :return: dictionary containing the periods in the specified in which instances are running as well as the % saving
        in running hours
        """
        if name is None or len(name) == 0:
            raise ValueError(ERR_GET_USAGE_SCHEDULE_NAME_EMPTY)

        schedule = self.configuration.get_schedule(name)
        if schedule is None:
            raise ValueError(ERR_SCHEDULE_NOT_FOUND.format(name))

        if startdate:
            if not isinstance(startdate, datetime):
                try:
                    start = datetime.strptime(startdate, "%Y%m%d").replace(
                        tzinfo=ZoneInfo(schedule.timezone)
                    )
                except ValueError as ex:
                    raise ValueError(
                        ERR_GET_USAGE_INVALID_START_DATE.format(startdate, str(ex))
                    )
            else:
                start = startdate
        else:
            tz = ZoneInfo(schedule.timezone)
            start = startdate or datetime.now(tz)

        if enddate:
            if not isinstance(enddate, datetime):
                try:
                    end = datetime.strptime(enddate, "%Y%m%d").replace(
                        tzinfo=ZoneInfo(schedule.timezone)
                    )
                except ValueError as ex:
                    raise ValueError(
                        ERR_GET_USAGE_INVALID_END_DATE.format(enddate, str(ex))
                    )
            else:
                end = enddate
        else:
            end = start

        if start > end:
            raise ValueError(ERR_GET_USAGE_START_MUST_BE_LESS_OR_EQUAL_STOP)

        periods = self.calculate_schedule_usage_for_period(
            name, start_dt=start, stop_dt=end
        )

        # to json and back again using custom encoder to convert datetimes
        return ConfigAdmin._for_output(periods)

    @staticmethod
    def _for_output(item: Any) -> Any:
        # to anf from json using custom encoder to convert datetime and set type data into string and lists
        return json.loads(json.dumps(item, cls=ConfigAdmin.CustomEncoder))

    @staticmethod
    def _ensure_set(s: list[str] | set[str] | str) -> set[str]:
        if isinstance(s, list):
            return set(s)
        if isinstance(s, str):
            return set(s.split(","))
        return s

    @staticmethod
    def _ensure_bool(b: Any) -> Optional[bool]:
        s = str(b).lower()
        if s == "true":
            return True
        if s == "false":
            return False
        return None

    def _validate_period(self, period: ConfigTablePeriodItem) -> ConfigTablePeriodItem:
        result: ConfigTablePeriodItem = {}

        def is_valid_time(s: Any) -> bool:
            return re.match(ConfigAdmin.TIME_REGEX, s) is not None

        # allowed and validated parameters
        valid_parameters = [
            configuration.BEGINTIME,
            configuration.ENDTIME,
            configuration.WEEKDAYS,
            configuration.MONTHDAYS,
            configuration.MONTHS,
            configuration.NAME,
            configuration.DESCRIPTION,
        ]

        for attr in period:
            # indicates type for config entry
            if attr == ConfigAdmin.TYPE_ATTR:
                continue

            # parameter is allowed?
            if attr not in valid_parameters:
                raise ValueError(
                    ERR_PERIOD_UNKNOWN_PARAMETER.format(attr, str(valid_parameters))
                )

            # remove None values
            if period[attr] is None or len(str(period[attr])) == 0:  # type: ignore[literal-required]
                continue

            # period name
            if attr == configuration.NAME:
                result[attr] = period[attr]  # type: ignore[literal-required]
                continue

            # description
            if attr == configuration.DESCRIPTION:
                result[attr] = period[attr]  # type: ignore[literal-required]
                continue

            # validate start and end types times
            if attr in [configuration.BEGINTIME, configuration.ENDTIME]:
                time_str = period[attr]  # type: ignore[literal-required]
                if not is_valid_time(time_str):
                    raise ValueError(ERR_PERIOD_INVALID_TIME.format(attr, time_str))
                result[attr] = str(  # type: ignore[literal-required]
                    datetime.strptime(time_str, configuration.TIME_FORMAT_STRING).time()
                )[0 : len(configuration.TIME_FORMAT_STRING)]
                if (
                    configuration.BEGINTIME in result
                    and configuration.ENDTIME in result
                ):
                    begintime = datetime.strptime(
                        result["begintime"],
                        configuration.TIME_FORMAT_STRING,
                    ).time()
                    endtime = datetime.strptime(
                        result["endtime"], configuration.TIME_FORMAT_STRING
                    ).time()
                    if begintime > endtime:
                        raise ValueError(
                            ERR_PERIOD_BEGIN_LATER_THAN_END.format(
                                result["begintime"],
                                result["endtime"],
                            )
                        )

                continue

            # check weekdays, monthdays and month sets
            if attr in [
                configuration.WEEKDAYS,
                configuration.MONTHDAYS,
                configuration.MONTHS,
            ]:
                temp = self._ensure_set(period[attr])  # type: ignore[literal-required]

                if len(temp) == 0:
                    continue

                # validate month
                if attr == configuration.MONTHS:
                    try:
                        MonthSetBuilder().build(temp)
                        result[attr] = temp  # type: ignore[literal-required]
                        continue
                    except Exception:
                        raise ValueError(
                            ERR_PERIOD_INVALID_MONTHS.format(str(period[attr]))  # type: ignore[literal-required]
                        )

                # validate weekdays
                if attr == configuration.WEEKDAYS:
                    try:
                        wdb = WeekdaySetBuilder(year=2016, month=12, day=31)
                        wdb.build(temp)
                        result[attr] = temp  # type: ignore[literal-required]
                        continue
                    except Exception as ex:
                        raise ValueError(
                            ERR_PERIOD_INVALID_WEEKDAYS.format(str(period[attr]), ex)  # type: ignore[literal-required]
                        )

                # validate monthdays
                if attr == configuration.MONTHDAYS:
                    try:
                        MonthdaySetBuilder(year=2016, month=12).build(temp)
                        result[attr] = temp  # type: ignore[literal-required]
                        continue
                    except Exception:
                        raise ValueError(
                            ERR_PERIOD_INVALID_MONTHDAYS.format(str(period[attr]))  # type: ignore[literal-required]
                        )

        if configuration.NAME not in result:
            raise ValueError(ERR_NAME_PARAM_MISSING)

        for condition in [
            configuration.BEGINTIME,
            configuration.ENDTIME,
            configuration.WEEKDAYS,
            configuration.MONTHS,
            configuration.MONTHDAYS,
        ]:
            if condition in result:
                break
        else:
            raise ValueError(ERR_NO_PERIODS)

        result["type"] = "period"

        return result

    # check schedule before writing it to the database
    def _validate_schedule(
        self, schedule: ConfigTableScheduleItem
    ) -> ConfigTableScheduleItem:
        validated_schedule: ConfigTableScheduleItem = {}

        # allowed parameters
        valid_parameters = [
            configuration.TIMEZONE,
            configuration.PERIODS,
            configuration.NAME,
            configuration.DESCRIPTION,
            configuration.OVERWRITE,
            configuration.METRICS,
            configuration.STOP_NEW_INSTANCES,
            configuration.USE_MAINTENANCE_WINDOW,
            configuration.SSM_MAINTENANCE_WINDOW,
            configuration.RETAINED_RUNNING,
            configuration.ENFORCED,
            configuration.HIBERNATE,
            configuration.OVERRIDE_STATUS,
            configuration.SCHEDULE_CONFIG_STACK,
        ]

        for attr in schedule:
            if attr == ConfigAdmin.TYPE_ATTR:
                continue

            if attr not in valid_parameters:
                raise ValueError(
                    ERR_SCHEDULE_UNKNOWN_PARAMETER.format(attr, valid_parameters)
                )

            # skip None values
            if schedule[attr] is None or len(str(schedule[attr])) == 0:  # type: ignore[literal-required]
                continue

            # check periods set
            if attr == configuration.PERIODS:
                temp = self._ensure_set(schedule[attr])  # type: ignore[literal-required]
                if len(temp) > 0:
                    validated_schedule[attr] = temp  # type: ignore[literal-required]
                continue

            if attr in [configuration.NAME, configuration.SSM_MAINTENANCE_WINDOW]:
                validated_schedule[attr] = schedule[attr]  # type: ignore[literal-required]
                continue

            # make sure these fields are valid booleans
            if attr in [
                configuration.METRICS,
                configuration.STOP_NEW_INSTANCES,
                configuration.USE_MAINTENANCE_WINDOW,
                configuration.RETAINED_RUNNING,
                configuration.HIBERNATE,
                configuration.ENFORCED,
            ]:
                bool_value = self._ensure_bool(schedule[attr])  # type: ignore[literal-required]
                if bool_value is None:
                    raise ValueError(
                        ERR_SCHEDULE_INVALID_BOOLEAN.format(schedule[attr], attr)  # type: ignore[literal-required]
                    )
                validated_schedule[attr] = bool_value  # type: ignore[literal-required]
                continue

            # overwrite status, now deprecated, use PROP_OVERRIDE_STATUS instead
            if attr == configuration.OVERWRITE:
                if configuration.OVERRIDE_STATUS in schedule:
                    raise ValueError(
                        ERR_SCHEDULE_OVERWRITE_OVERRIDE_EXCLUSIVE.format(
                            configuration.OVERWRITE, configuration.OVERRIDE_STATUS
                        )
                    )

                bool_value = self._ensure_bool(schedule[attr])  # type: ignore[literal-required]
                if bool_value is None:
                    raise ValueError(
                        ERR_SCHEDULE_INVALID_BOOLEAN.format(schedule[attr], attr)  # type: ignore[literal-required]
                    )
                validated_schedule["override_status"] = (
                    "running" if bool_value else "stopped"
                )
                continue

            if attr == configuration.OVERRIDE_STATUS:
                if configuration.OVERWRITE in schedule:
                    raise ValueError(
                        ERR_SCHEDULE_OVERWRITE_OVERRIDE_EXCLUSIVE.format(
                            configuration.OVERWRITE, configuration.OVERRIDE_STATUS
                        )
                    )
                if schedule[attr] not in configuration.OVERRIDE_STATUS_VALUES:  # type: ignore[literal-required]
                    raise ValueError(
                        ERR_SCHEDULE_INVALID_OVERRIDE.format(
                            schedule[attr],  # type: ignore[literal-required]
                            attr,
                            ",".join(configuration.OVERRIDE_STATUS_VALUES),
                        )
                    )
                validated_schedule[attr] = schedule[attr]  # type: ignore[literal-required]
                continue

            # description
            if attr in [configuration.DESCRIPTION, configuration.SCHEDULE_CONFIG_STACK]:
                validated_schedule[attr] = schedule[attr]  # type: ignore[literal-required]
                continue

            # validate timezone
            if attr == configuration.TIMEZONE:
                timezone = schedule[configuration.TIMEZONE]  # type: ignore[literal-required]
                if not SchedulerConfigBuilder.is_valid_timezone(timezone):
                    raise ValueError(
                        ERR_SCHEDULE_INVALID_TIMEZONE.format(
                            timezone, configuration.TIMEZONE
                        )
                    )
                validated_schedule[attr] = timezone  # type: ignore[literal-required]

        # name is mandatory
        if configuration.NAME not in validated_schedule:
            raise ValueError(ERR_SCHEDULE_NAME_MISSING)

        # if there is no overwrite there must be at least one period
        if configuration.OVERRIDE_STATUS not in schedule and (
            configuration.PERIODS not in schedule
            or len(schedule[configuration.PERIODS]) == 0  # type: ignore[literal-required]
        ):
            raise ValueError(ERR_SCHEDULE_NO_PERIOD)

        # validate if periods are in configuration
        if configuration.PERIODS in validated_schedule:
            # get list of all configured periods
            periods_from_db = [p[configuration.NAME] for p in self._list_periods()]

            configured_periods = validated_schedule["periods"]
            if not isinstance(
                configured_periods, set
            ):  # should be impossible, but mypy cannot currently prove it
                raise ValueError(
                    "Expected configuration periods to be a string set but received {} instead",
                    type(configured_periods),
                )

            for configured_period in configured_periods:
                # todo: this behavior of splitting period names to get Instance_type is too widely known and needs
                # todo: to be centralized somewhere
                if (
                    configured_period.split(configuration.INSTANCE_TYPE_SEP)[0]
                    not in periods_from_db
                ):
                    raise ValueError(
                        ERR_SCHEDULE_PERIOD_DOES_NOT_EXISTS.format(configured_period)
                    )

        # indicates this is a schedule
        validated_schedule["type"] = "schedule"

        return validated_schedule

    def _items_of_type(self, config_type: ConfigTableItemType) -> list[Any]:
        result = []

        args = {"FilterExpression": Key("type").eq(config_type), "ConsistentRead": True}

        while True:
            resp = self._table.scan(**args)  # todo: why are we doing a scan here?
            result += resp.get("Items", [])
            if "LastEvaluatedKey" in resp:
                args["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
            else:
                break

        return result

    def _list_schedules(self) -> list[Any]:
        return self._items_of_type("schedule")

    def _list_periods(self) -> list[Any]:
        return self._items_of_type("period")

    def _get_schedule(self, schedule_name: str) -> Any:
        resp = self._table.get_item(
            Key={"name": schedule_name, "type": "schedule"}, ConsistentRead=True
        )
        return resp.get("Item", None)

    def _get_period(self, period_name: str) -> Any:
        resp = self._table.get_item(
            Key={"name": period_name, "type": "period"}, ConsistentRead=True
        )
        return resp.get("Item", None)

    def calculate_schedule_usage_for_period(
        self,
        schedule_name: str,
        start_dt: datetime,
        stop_dt: Optional[datetime] = None,
        logger: Optional[Logger] = None,
    ) -> dict[str, Any]:
        result = {}

        def running_seconds(startdt: datetime, stopdt: datetime) -> int:
            return max(int((stopdt - startdt).total_seconds()), 60)

        def running_hours(startdt: datetime, stopdt: datetime) -> int:
            return int(((stopdt - startdt).total_seconds() - 1) / 3600) + 1

        def make_period(started_dt: Any, stopped_dt: Any) -> dict[str, Any]:
            running_period = {
                "begin": started_dt,
                "end": stopped_dt,
                "billing_hours": running_hours(started_dt, stopped_dt),
                "billing_seconds": running_seconds(started_dt, stopped_dt),
            }
            return running_period

        self._logger = logger

        stop = stop_dt or start_dt
        if start_dt > stop:
            raise ValueError(ERR_STOP_MUST_BE_LATER_OR_EQUAL_TO_START)

        dt = (
            start_dt
            if isinstance(start_dt, datetime)
            else datetime(start_dt.year, start_dt.month, start_dt.day)
        )

        config_data = ConfigDynamodbAdapter(self._table.name).config

        while dt <= stop:
            self._configuration = SchedulerConfigBuilder(logger=self._logger).build(
                config_data
            )
            conf = SchedulerConfigBuilder(self._logger).build(config=config_data, dt=dt)
            schedule = conf.get_schedule(schedule_name)
            if schedule is None:
                raise ValueError

            timeline = {dt.replace(hour=0, minute=0)}
            for p in schedule.periods:
                begintime = p["period"].begintime
                endtime = p["period"].endtime
                if begintime is None and endtime is None:
                    timeline.add(dt.replace(hour=0, minute=0))
                    timeline.add(dt.replace(hour=23, minute=59))
                else:
                    if begintime:
                        timeline.add(
                            dt.replace(hour=begintime.hour, minute=begintime.minute)
                        )
                    if endtime:
                        timeline.add(
                            dt.replace(hour=endtime.hour, minute=endtime.minute)
                        )

            running_periods = {}
            started = None
            starting_period = None
            current_state: Optional[ScheduleState] = None
            inst = Instance(
                instance_str="instance",
                allow_resize=False,
                id="",
                hibernate=False,
                state="",
                state_name="",
                is_running=False,
                is_terminated=False,
                current_state="stopped",
                instancetype="",
                maintenance_window=None,
                tags={},
                name="",
                schedule_name="",
            )
            for tm in sorted(list(timeline)):
                desired_state, _, period = schedule.get_desired_state(
                    inst, tm, self._logger, False
                )

                if current_state != desired_state:
                    if desired_state == "running":
                        started = tm
                        current_state = "running"
                        starting_period = period
                    elif desired_state == "stopped":
                        stopped = tm
                        (
                            desired_state_with_adj_check,
                            __,
                            ___,
                        ) = schedule.get_desired_state(inst, tm, self._logger, True)
                        if desired_state_with_adj_check == "running":
                            stopped += timedelta(minutes=1)
                        if current_state == "running":
                            current_state = "stopped"
                            running_periods[starting_period] = make_period(
                                started, stopped
                            )

            if current_state == "running":
                stopped = dt.replace(hour=23, minute=59) + timedelta(minutes=1)
                running_periods[starting_period] = make_period(started, stopped)

            result[str(dt.date())] = {
                "running_periods": running_periods,
                "billing_seconds": sum(
                    [running_periods[ps]["billing_seconds"] for ps in running_periods]
                ),
                "billing_hours": sum(
                    [running_periods[ph]["billing_hours"] for ph in running_periods]
                ),
            }

            dt += timedelta(days=1)

        return {"schedule": schedule_name, "usage": result}
