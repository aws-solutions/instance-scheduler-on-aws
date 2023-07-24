# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import datetime
import re as regex
import time
import zoneinfo
from typing import TYPE_CHECKING, Any, Optional
from zoneinfo import ZoneInfo

from boto3.session import Session

from instance_scheduler import boto_retry, configuration
from instance_scheduler.configuration.instance_schedule import InstanceSchedule
from instance_scheduler.configuration.running_period import RunningPeriod
from instance_scheduler.configuration.scheduler_config import GlobalConfig
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
from instance_scheduler.util.logger import Logger

if TYPE_CHECKING:
    from mypy_boto3_ssm.client import SSMClient
else:
    SSMClient = object

REGEX_SSM_PARAM = "{param:(.+?)}"


MSG_BEGIN_MUST_BEFORE_END = "Begin time {} must be earlier than end time in {}"
MSG_DUPLICATE_PERIOD_NAME_FOUND = 'Duplicate period name "{}" found'
MSG_DUPLICATE_SCHEDULE_NAME_FOUND = 'Duplicate schedule name "{}" found'
MSG_INVALID_DEFAULT_TIMEZONE = '"{}" is not a valid timezone, use zoneinfo.available_timezones() to list all valid zones'
MSG_INVALID_OVERRIDE_STATUS = "{} is not a valid value for {}, possible values are {}"
MSG_NAME_MISSING_IN_PERIOD = 'Name missing in period "{}"'
MSG_NAME_MISSING_IN_SCHEDULE = "Name missing in schedule {}"
MSG_OVERWRITE_OVERRIDE_MUTUAL_EXCLUSIVE = "{} and {} are mutually exclusive options"
MSG_SCHEDULE_IS_NOT_DEFINED = 'Period "{}" used in schedule "{}" is not defined'
MSG_TAGNAME_MISSING_IN_CONFIGURATION = "tagname is missing in configuration"
MSG_INVALID_SCHEDULE_TIMEZONE = (
    '"{}" is in schedule config "{}" is not a valid timezone, check zoneinfo.available_timezones() for '
    "valid zones"
)


class SchedulerConfigBuilder:
    """
    Class that implements logic for building the configuration from the raw stored configuration data.
    """

    _checked_timezones: dict[str, Any] = dict()
    _invalid_timezones: set[str] = set()
    _all_timezones = {tz.lower(): tz for tz in zoneinfo.available_timezones()}

    def __init__(self, logger: Optional[Logger]) -> None:
        self._logger = logger
        self._config: Any = None
        self._ssm: Optional[SSMClient] = None

    @property
    def ssm(self) -> SSMClient:
        if self._ssm is None:
            self._ssm = boto_retry.get_client_with_standard_retry("ssm")
        return self._ssm

    def build(
        self, config: dict[Any, Any], dt: Optional[datetime.datetime] = None
    ) -> GlobalConfig:
        self._config = config

        config_date = dt if dt is not None else datetime.datetime.now()

        try:
            scheduler_metrics = config.get(configuration.METRICS, False)

            remote_account_ids_from_ssm = self.get_remote_account_ids_from_ssm(config)

            app_env = get_app_env()

            session = Session()
            aws_partition = session.get_partition_for_region(session.region_name)

            return GlobalConfig(
                scheduled_services=app_env.scheduled_services(),
                schedule_clusters=app_env.enable_rds_clusters,
                create_rds_snapshot=app_env.enable_rds_snapshots,
                tag_name=app_env.schedule_tag_key,
                regions=app_env.schedule_regions,
                default_timezone=app_env.default_timezone,
                schedules=self._build_schedules(
                    config,
                    str(app_env.default_timezone),
                    scheduler_metrics,
                    config_date,
                ),
                trace=app_env.enable_debug_logging,
                enable_ssm_maintenance_windows=app_env.enable_ec2_ssm_maintenance_windows,
                use_metrics=app_env.enable_cloudwatch_metrics,
                remote_account_ids=remote_account_ids_from_ssm,
                aws_partition=aws_partition,
                namespace=app_env.app_namespace,
                scheduler_role_name=app_env.scheduler_role_name,
                organization_id=config.get(configuration.ORGANIZATION_ID, ""),
                schedule_lambda_account=app_env.enable_schedule_hub_account,
                started_tags=",".join(app_env.start_tags),
                stopped_tags=",".join(app_env.stop_tags),
            )
        except ValueError as ex:
            if self._logger is not None:
                self._logger.error(str(ex))
            raise ex

    def get_remote_account_ids_from_ssm(self, config: dict[Any, Any]) -> list[str]:
        remote_account_ids_from_ssm = []
        for account_id in config.get(configuration.REMOTE_ACCOUNT_IDS, []) or []:
            if regex.match(REGEX_SSM_PARAM, account_id):
                account = regex.findall(REGEX_SSM_PARAM, account_id)
                if len(account) > 0:
                    resp = self.ssm.get_parameters(Names=list(set(account)))
                    for p in resp.get("Parameters", []):
                        if p["Type"] == "StringList":
                            remote_account_ids_from_ssm += p["Value"].split(",")
                        else:
                            remote_account_ids_from_ssm.append(p["Value"])
            else:
                remote_account_ids_from_ssm.append(account_id)
        return remote_account_ids_from_ssm

    # build the schedules from the configuration
    def _build_schedules(
        self,
        conf: Any,
        dflt_tz: str,
        scheduler_use_metrics: bool,
        dt: datetime.datetime,
    ) -> dict[str, InstanceSchedule]:
        schedules = {}

        # use the periods to build the schedules that can be assigned to the instances
        for schedule_config in conf.get(configuration.SCHEDULES, []):
            schedule = self._build_schedule(
                schedule_config, dflt_tz, scheduler_use_metrics, dt
            )
            if schedule is None:
                continue
            if schedule.name in schedules:
                if self._logger is not None:
                    self._logger.error(MSG_DUPLICATE_SCHEDULE_NAME_FOUND, schedule.name)
                continue

            schedules[schedule.name] = schedule

        return schedules

    def _build_schedule(
        self,
        schedule_config: Any,
        dflt_tz: str,
        scheduler_use_config: bool,
        dt: datetime.datetime,
    ) -> Optional[InstanceSchedule]:
        # gets the timezone
        def get_timezone(schedule_configuration: Any) -> str:
            schedule_timezone = schedule_configuration.get(configuration.TIMEZONE)
            if not schedule_timezone:
                schedule_timezone = dflt_tz

            validated = SchedulerConfigBuilder.validated_timezone(schedule_timezone)
            if validated is None:
                raise ValueError(
                    MSG_INVALID_SCHEDULE_TIMEZONE.format(
                        schedule_timezone, schedule_configuration
                    )
                )
            return validated

        def get_schedule_name(config):
            schedule_name = config.get(configuration.NAME, None)
            if not schedule_name:
                raise ValueError(MSG_NAME_MISSING_IN_SCHEDULE.format(config))
            return schedule_name

        def get_override_status(config):
            if configuration.OVERWRITE in config:
                if configuration.OVERRIDE_STATUS in config:
                    raise ValueError(
                        MSG_OVERWRITE_OVERRIDE_MUTUAL_EXCLUSIVE.format(
                            configuration.OVERWRITE, configuration.OVERRIDE_STATUS
                        )
                    )
                overwrite = config[configuration.OVERWRITE]
                return (
                    configuration.OVERRIDE_STATUS_RUNNING
                    if overwrite
                    else configuration.OVERRIDE_STATUS_STOPPED
                )
            status = config.get(configuration.OVERRIDE_STATUS, None)
            if (
                status is not None
                and status not in configuration.OVERRIDE_STATUS_VALUES
            ):
                raise ValueError(
                    MSG_INVALID_OVERRIDE_STATUS.format(
                        status,
                        configuration.OVERRIDE_STATUS,
                        ",".join(configuration.OVERRIDE_STATUS_VALUES),
                    )
                )
            return status

        try:
            timezone = get_timezone(schedule_config)
            override_status = get_override_status(schedule_config)
            periods_for_schedule = []

            # ignore periods if there is an always on or if override_status option is used
            if not override_status:
                # use current date and time for timezone of schedule
                current_schema_dt = dt.now(
                    SchedulerConfigBuilder._get_timezone(timezone)
                )
                periods_for_schedule = self._get_schedule_periods(
                    schedule_config, current_schema_dt
                )

            return InstanceSchedule(
                name=get_schedule_name(schedule_config),
                periods=periods_for_schedule,
                timezone=timezone,
                override_status=override_status,
                description=schedule_config.get(configuration.DESCRIPTION, ""),
                use_metrics=schedule_config.get(
                    configuration.METRICS, scheduler_use_config
                ),
                stop_new_instances=schedule_config.get(
                    configuration.STOP_NEW_INSTANCES, True
                ),
                use_maintenance_window=schedule_config.get(
                    configuration.USE_MAINTENANCE_WINDOW, False
                ),
                ssm_maintenance_window=schedule_config.get(
                    configuration.SSM_MAINTENANCE_WINDOW, None
                ),
                enforced=schedule_config.get(configuration.ENFORCED, False),
                hibernate=schedule_config.get(configuration.HIBERNATE, False),
                retain_running=schedule_config.get(configuration.RETAINED_RUNNING),
                configured_in_stack=schedule_config.get("configured_in_stack", None),
            )

        except ValueError as ex:
            if self._logger is not None:
                self._logger.error(str(ex))
            return None

    def _get_schedule_periods(self, schedule_config, schema_dt):
        def get_config_for_period(period_name):
            for cfg in self._config.get(configuration.PERIODS, []):
                if configuration.NAME in cfg and cfg[configuration.NAME] == period_name:
                    return cfg
            return None

        schedule_periods = []

        for period_config in schedule_config.get(configuration.PERIODS, []):
            instancetype = None
            if configuration.INSTANCE_TYPE_SEP in period_config:
                name, instancetype = period_config.rsplit(
                    configuration.INSTANCE_TYPE_SEP, 1
                )
            else:
                name = period_config

            period_config = get_config_for_period(name)
            if period_config is None:
                raise ValueError(
                    MSG_SCHEDULE_IS_NOT_DEFINED.format(name, schedule_config)
                )

            new_period = self._build_period(period_config, schema_dt)

            schedule_periods.append(
                {"period": new_period, "instancetype": instancetype}
            )

        return schedule_periods

    @staticmethod
    def get_time_from_string(timestr: str) -> Optional[datetime.time]:
        """
        Standardised method to build time object instance from time string
        :param timestr: string in format as defined in configuration.TIME_FORMAT_STRING
        :return: time object from time string, None if the time is invalid
        """
        if not timestr:
            return None
        try:
            tm = time.strptime(timestr, configuration.TIME_FORMAT_STRING)
        except ValueError:
            return None
        return datetime.time(tm.tm_hour, tm.tm_min, 0)

    @classmethod
    def _build_period(cls, period_configuration, dt):
        def get_periodname(config):
            period_name = config.get(configuration.NAME)
            if not period_name:
                raise ValueError(MSG_NAME_MISSING_IN_PERIOD.format(config))
            return period_name

        # reads a start and end time from config
        def get_begin_and_end(period_name, config):
            begin = SchedulerConfigBuilder.get_time_from_string(
                config.get(configuration.BEGINTIME)
            )
            end = SchedulerConfigBuilder.get_time_from_string(
                config.get(configuration.ENDTIME)
            )
            if (begin and end) and begin > end:
                raise ValueError(
                    MSG_BEGIN_MUST_BEFORE_END.format(begin, end, period_name)
                )
            return begin, end

        def build_period_config_set(period_config, set_builder, config_name):
            config_set = period_config.get(config_name)
            if config_set:
                return set_builder.build(config_set)
            else:
                return None

        name = get_periodname(period_configuration)
        begin_time, end_time = get_begin_and_end(name, period_configuration)

        week_days = build_period_config_set(
            period_configuration,
            WeekdaySetBuilder(year=dt.year, month=dt.month, day=dt.day),
            configuration.WEEKDAYS,
        )
        months = build_period_config_set(
            period_configuration, MonthSetBuilder(), configuration.MONTHS
        )
        monthdays = build_period_config_set(
            period_configuration,
            MonthdaySetBuilder(year=dt.year, month=dt.month),
            configuration.MONTHDAYS,
        )

        return RunningPeriod(
            name=name,
            begintime=begin_time,
            endtime=end_time,
            weekdays=week_days,
            months=months,
            monthdays=monthdays,
        )

    @staticmethod
    def is_valid_timezone(tz: str) -> bool:
        """
        Generic and optimized method to test the validity of a timezone name
        :param tz:
        :return: True if the timezone is valid, else False
        """
        return SchedulerConfigBuilder.validated_timezone(tz) is not None

    @staticmethod
    def validated_timezone(tz: str) -> Optional[str]:
        """
        Generic and optimized method to get a timezone from a timezone name
        :param tz: name of the timezone
        :return: timezone instance, None if it not valid
        """
        tz_lower = str(tz).lower()
        # -----------cache----------------#
        if tz_lower in SchedulerConfigBuilder._checked_timezones:
            return str(SchedulerConfigBuilder._checked_timezones[tz_lower])

        if tz_lower in SchedulerConfigBuilder._invalid_timezones:
            return None

        # -----------check----------------#
        validated = SchedulerConfigBuilder._all_timezones.get(tz_lower, None)
        if validated is not None:
            # keep list off approved timezones to make next checks much faster
            SchedulerConfigBuilder._checked_timezones[tz_lower] = ZoneInfo(validated)
            return validated
        else:
            SchedulerConfigBuilder._invalid_timezones.add(tz_lower)
        return None

    @staticmethod
    def _get_timezone(tz_name):
        tz_lower = str(tz_name).lower()
        # did we use this one before, reuse it
        tz = SchedulerConfigBuilder._checked_timezones.get(tz_lower)
        if tz is not None:
            return tz

        # avoid repeated lookup for invalid timezones
        if tz_lower not in SchedulerConfigBuilder._invalid_timezones:
            # case insensitive lookup for timezone name
            tz_str = SchedulerConfigBuilder._all_timezones.get(tz_lower)
            if tz_str is not None:
                # found it, no need to check for invalid timezone here because of lookup
                tz = ZoneInfo(tz_str)
                SchedulerConfigBuilder._checked_timezones[tz_lower] = tz
                return tz

            # not a valid timezone
            SchedulerConfigBuilder._invalid_timezones.add(tz_lower)

        raise ValueError("Timezone {} is not a valid timezone".format(tz_name))
