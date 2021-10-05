######################################################################################################################
#  Copyright 2021 Amazon.com, Inc. or its affiliates. All Rights Reserved.                                           #
#                                                                                                                    #
#  Licensed under the Apache License Version 2.0 (the "License"). You may not use this file except in compliance     #
#  with the License. A copy of the License is located at                                                             #
#                                                                                                                    #
#      http://www.apache.org/licenses/                                                                               #
#                                                                                                                    #
#  or in the "license" file accompanying this file. This file is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES #
#  OR CONDITIONS OF ANY KIND, express or implied. See the License for the specific language governing permissions    #
#  and limitations under the License.                                                                                #
######################################################################################################################

import datetime
import time

import dateutil.parser

import configuration
import pytz
import re as regex
import boto3
from util import get_config
from configuration.instance_schedule import InstanceSchedule
from configuration.running_period import RunningPeriod
from configuration.scheduler_config import SchedulerConfig
from configuration.setbuilders.month_setbuilder import MonthSetBuilder
from configuration.setbuilders.monthday_setbuilder import MonthdaySetBuilder
from configuration.setbuilders.weekday_setbuilder import WeekdaySetBuilder


ATTR_BEGINTIME = "begintime"
ATTR_REMOTE_ACCOUNT_IDS = "remote_account_ids"
ATTR_ORGANIZATION_ID = "organization_id"
ATTR_CREATE_RDS_SNAPSHOT = "create_rds_snapshot"
ATTR_DEFAULT_TIMEZONE = "default_timezone"
ATTR_ENDTIME = "endtime"
ATTR_MONTHDAYS = "monthdays"
ATTR_MONTHS = "months"
ATTR_NAME = "name"
ATTR_PERIOD = "period"
ATTR_PERIODS = "periods"
ATTR_REGIONS = "regions"
ATTR_SCHEDULE_DT = "schedule_dt"
ATTR_SCHEDULED_SERVICES = "scheduled_services"
ATTR_SCHEDULE_CLUSTERS = "schedule_clusters"
ATTR_SCHEDULES = "schedules"
ATTR_STARTED_TAGS = "started_tags"
ATTR_STOPPED_TAGS = "stopped_tags"
ATTR_TAGNAME = "tag_name"
ATTR_TIMEZONE = "timezone"
ATTR_TRACE = "trace"
ATTR_WEEKDAYS = "weekdays"
ATTR_NAMESPACE = "namespace"
ATTR_EXECUTION_ROLE_NAME = "execution_role_name"
ATTR_AWS_PARTITION = "aws_partition"

MSG_BEGIN_MUST_BEFORE_END = "Begin time {} must be earlier than end time in {}"
MSG_DUPLICATE_PERIOD_NAME_FOUND = "Duplicate period name \"{}\" found"
MSG_DUPLICATE_SCHEDULE_NAME_FOUND = "Duplicate schedule name \"{}\" found"
MSG_INVALID_DEFAULT_TIMEZONE = "\"{}\" is not a valid timezone, use pytz.all_timezones to list all valid zones"
MSG_NAME_MISSING_IN_PERIOD = "Name missing in period \"{}\""
MSG_NAME_MISSING_IN_SCHEDULE = "Name missing in schedule {}"
MSG_OVERWRITE_OVERRIDE_MUTUAL_EXCLUSIVE = "{} and {} are mutually exclusive options"
MSG_SCHEDULE_IS_NOT_DEFINED = "Period \"{}\" used in schedule \"{}\" is not defined"
MSG_TAGNAME_MISSING_IN_CONFIGURATION = "tagname is missing in configuration"
MSG_INVALID_SCHEDULE_TIMEZONE = "\"{}\" is in schedule config \"{}\" is not a valid timezone, check pytz.all_timezone for " \
                                "valid zones"


class SchedulerConfigBuilder:
    """
    Class that implements logic for building the configuration from the raw stored configuration data.
    """
    _checked_timezones = dict()
    _invalid_timezones = set()
    _all_timezones = {tz.lower(): tz for tz in pytz.all_timezones}

    def __init__(self, logger):
        self._logger = logger
        self._config = None
        self._ssm = None

    @property
    def ssm(self):
        if self._ssm is None:
            self._ssm = boto3.client('ssm', config=get_config())
        return self._ssm

    def build(self, config, dt=None):

        def get_scheduler_tagname(config_data):
            name = config_data.get(configuration.TAGNAME, configuration.DEFAULT_TAGNAME)
            if not name or len(name) == 0:
                raise ValueError(MSG_TAGNAME_MISSING_IN_CONFIGURATION)
            return name

        def get_default_timezone(config_data):
            tz = config_data.get(configuration.DEFAULT_TIMEZONE, configuration.DEFAULT_TZ)
            validated = SchedulerConfigBuilder.validated_timezone(tz)
            if validated is None:
                raise ValueError(MSG_INVALID_DEFAULT_TIMEZONE.format(tz))
            return validated

        self._config = config

        config_date = dt if dt is not None else datetime.datetime.now()

        try:

            return SchedulerConfig(scheduled_services=config.get(configuration.SCHEDULED_SERVICES, []) or [],
                                   schedule_clusters=config.get(configuration.SCHEDULE_CLUSTERS, False),
                                   create_rds_snapshot=config.get(configuration.CREATE_RDS_SNAPSHOT, True),
                                   tag_name=get_scheduler_tagname(config),
                                   regions=config.get(configuration.REGIONS, []) or [],
                                   default_timezone=get_default_timezone(config),
                                   schedules=self._build_schedules(config, get_default_timezone(config), config_date),
                                   trace=config.get(configuration.TRACE, False),
                                   namespace=config.get(configuration.NAMEPSACE, ""),
                                   execution_role_name=config.get(configuration.EXECUTION_ROLE_NAME, ""),
                                   aws_partition=config.get(configuration.AWS_PARTITION, ""),
                                   remote_account_ids=config.get(configuration.REMOTE_ACCOUNT_IDS, []),
                                   organization_id=config.get(configuration.ORGANIZATION_ID, ""),
                                   started_tags=config.get(configuration.STARTED_TAGS, ""),
                                   stopped_tags=config.get(configuration.STOPPED_TAGS, ""))
        except ValueError as ex:
            if self._logger is not None:
                self._logger.error(str(ex))
            return None

    # build the schedules from the configuration
    def _build_schedules(self, conf, dflt_tz, dt):
        schedules = {}

        # use the periods to build the schedules that can be assigned to the instances
        for schedule_config in conf.get(configuration.SCHEDULES, []):
            schedule = self._build_schedule(schedule_config, dflt_tz, dt)
            if schedule is None:
                continue
            if schedule.name in schedules:
                if self._logger is not None:
                    self._logger.error(MSG_DUPLICATE_SCHEDULE_NAME_FOUND, schedule.name)
                continue

            schedules[schedule.name] = schedule

        return schedules

    def _build_schedule(self, schedule_config, dflt_tz, dt):

        # gets the timezone
        def get_timezone(schedule_configuration):
            schedule_timezone = schedule_configuration.get(configuration.TIMEZONE)
            if not schedule_timezone:
                schedule_timezone = dflt_tz

            validated = SchedulerConfigBuilder.validated_timezone(schedule_timezone)
            if validated is None:
                raise ValueError(MSG_INVALID_SCHEDULE_TIMEZONE.format(schedule_timezone, schedule_configuration))
            return validated

        def get_schedule_name(config):
            schedule_name = config.get(configuration.NAME, None)
            if not schedule_name:
                raise ValueError(MSG_NAME_MISSING_IN_SCHEDULE.format(config))
            return schedule_name

        try:

            timezone = get_timezone(schedule_config)
            periods_for_schedule = []

            current_schema_dt = dt.now(SchedulerConfigBuilder._get_timezone(timezone))
            periods_for_schedule = self._get_schedule_periods(schedule_config, current_schema_dt)

            return InstanceSchedule(name=get_schedule_name(schedule_config),
                                    periods=periods_for_schedule,
                                    timezone=timezone,
                                    description=schedule_config.get(configuration.DESCRIPTION, ""))

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
                name, instancetype = period_config.rsplit(configuration.INSTANCE_TYPE_SEP, 1)
            else:
                name = period_config

            period_config = get_config_for_period(name)
            if period_config is None:
                raise ValueError(MSG_SCHEDULE_IS_NOT_DEFINED.format(name, schedule_config))

            new_period = self._build_period(period_config, schema_dt)

            schedule_periods.append({"period": new_period, "instancetype": instancetype})

        return schedule_periods

    @staticmethod
    def get_time_from_string(timestr):
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

            begin = SchedulerConfigBuilder.get_time_from_string(config.get(configuration.BEGINTIME))
            end = SchedulerConfigBuilder.get_time_from_string(config.get(configuration.ENDTIME))
            if (begin and end) and begin > end:
                raise ValueError(MSG_BEGIN_MUST_BEFORE_END.format(begin, end, period_name))
            return begin, end

        def build_period_config_set(period_config, set_builder, config_name):
            config_set = period_config.get(config_name)
            if config_set:
                return set_builder.build(config_set)
            else:
                return None

        name = get_periodname(period_configuration)
        begin_time, end_time = get_begin_and_end(name, period_configuration)

        week_days = build_period_config_set(period_configuration, WeekdaySetBuilder(year=dt.year, month=dt.month, day=dt.day),
                                            configuration.WEEKDAYS)
        months = build_period_config_set(period_configuration, MonthSetBuilder(), configuration.MONTHS)
        monthdays = build_period_config_set(period_configuration, MonthdaySetBuilder(year=dt.year, month=dt.month),
                                            configuration.MONTHDAYS)

        return RunningPeriod(name=name, begintime=begin_time, endtime=end_time, weekdays=week_days, months=months,
                             monthdays=monthdays)

    @staticmethod
    def configuration_from_dict(d):
        """
        This method builds a configuration object instance that is passed as a dictionary in the event of a lambda function
        :param d:
        :return:
        """

        config_args = {}
        for attr in [ATTR_TAGNAME,
                     ATTR_DEFAULT_TIMEZONE,
                     ATTR_TRACE,
                     ATTR_NAMESPACE,
                     ATTR_ORGANIZATION_ID,
                     ATTR_EXECUTION_ROLE_NAME,
                     ATTR_AWS_PARTITION,
                     ATTR_SCHEDULE_CLUSTERS,
                     ATTR_CREATE_RDS_SNAPSHOT,
                     ATTR_STARTED_TAGS,
                     ATTR_STOPPED_TAGS]:
            config_args[attr] = d.get(attr, None)

        for attr in [ATTR_REGIONS,
                     ATTR_REMOTE_ACCOUNT_IDS,
                     ATTR_SCHEDULED_SERVICES]:
            config_args[attr] = set(d.get(attr, []))

        periods = {}

        for period_name in d.get(ATTR_PERIODS, {}):
            period_data = d[ATTR_PERIODS][period_name]
            period_args = {ATTR_NAME: period_name}

            for attr in [ATTR_BEGINTIME, ATTR_ENDTIME]:
                if attr in period_data:
                    period_args[attr] = SchedulerConfigBuilder.get_time_from_string(period_data[attr])

            for attr in [ATTR_WEEKDAYS, ATTR_MONTHDAYS, ATTR_MONTHS]:
                if attr in period_data:
                    period_args[attr] = set(period_data.get(attr, None))

            period = RunningPeriod(**period_args)
            periods[period_name] = period

        config_args[ATTR_SCHEDULES] = {}

        for schedule_name in d.get(ATTR_SCHEDULES, {}):
            schedule_args = {}
            schedule_data = d[ATTR_SCHEDULES][schedule_name]
            for attr in [ATTR_NAME,
                         ATTR_TIMEZONE,
                         ]:
                schedule_args[attr] = schedule_data.get(attr, None)

            for attr in [ATTR_SCHEDULE_DT]:
                if attr in schedule_data:
                    schedule_args[attr] = dateutil.parser.parse(schedule_data[attr])

            schedule = InstanceSchedule(**schedule_args)
            config_args[ATTR_SCHEDULES][schedule_name] = schedule

        config = SchedulerConfig(**config_args)

        return config

    # noinspection PyTypeChecker
    @staticmethod
    def configuration_as_dict(config):
        """
        This method build a dictionary from a configuration instance to be passed safely in the event of a lambda function
        :param config:
        :return:
        """
        result = {}

        for attr in [ATTR_TAGNAME,
                     ATTR_DEFAULT_TIMEZONE,
                     ATTR_TRACE,
                     ATTR_NAMESPACE,
                     ATTR_EXECUTION_ROLE_NAME,
                     ATTR_ORGANIZATION_ID,
                     ATTR_AWS_PARTITION,
                     ATTR_SCHEDULE_CLUSTERS,
                     ATTR_CREATE_RDS_SNAPSHOT,
                     ATTR_STARTED_TAGS,
                     ATTR_STOPPED_TAGS]:
            if attr in config.__dict__ and config.__dict__[attr] is not None:
                result[attr] = config.__dict__[attr]

        for attr in [ATTR_STARTED_TAGS,
                     ATTR_STOPPED_TAGS]:
            if attr in config.__dict__ and config.__dict__[attr] is not None:
                result[attr] = ",".join(["{}={}".format(t["Key"], t["Value"]) for t in config.__dict__[attr]])

        for attr in [ATTR_REGIONS,
                     ATTR_REMOTE_ACCOUNT_IDS,
                     ATTR_SCHEDULED_SERVICES]:
            if len(config.__dict__[attr]) > 0:
                result[attr] = list(config.__dict__[attr])

        result[ATTR_SCHEDULES] = {}
        result[ATTR_PERIODS] = {}

        for schedule_name in config.schedules:
            result[ATTR_SCHEDULES][schedule_name] = {}
            schedule = config.schedules[schedule_name]
            for attr in [ATTR_NAME,
                         ATTR_TIMEZONE]:
                if attr in schedule.__dict__ and schedule.__dict__[attr] is not None:
                    result[ATTR_SCHEDULES][schedule_name][attr] = schedule.__dict__[attr]

            for attr in [ATTR_SCHEDULE_DT]:
                dt = schedule.__dict__[attr]
                if dt is not None:
                    result[ATTR_SCHEDULES][schedule.name][attr] = dt.isoformat()

            if schedule.override_status is not None:
                continue

            result[ATTR_SCHEDULES][schedule_name][ATTR_PERIODS] = []

            for p in schedule.periods:
                period = p[ATTR_PERIOD]
                result[ATTR_SCHEDULES][schedule_name][ATTR_PERIODS].append(
                    period.name)
                if period.name in result[ATTR_PERIODS]:
                    continue

                result[ATTR_PERIODS][period.name] = {}
                for attr in [ATTR_BEGINTIME,
                             ATTR_ENDTIME]:
                    tm = period.__dict__[attr]
                    if tm is not None:
                        result[ATTR_PERIODS][period.name][attr] = "{:0>2d}:{:0>2d}".format(tm.hour, tm.minute)

                for attr in [ATTR_WEEKDAYS,
                             ATTR_MONTHDAYS,
                             ATTR_MONTHS]:
                    s = period.__dict__[attr]
                    if s is None:
                        continue
                    result[ATTR_PERIODS][period.name][attr] = list(s)
        return result

    @staticmethod
    def is_valid_timezone(tz):
        """
        Generic and optimized method to test the validity of a timezone name
        :param tz:
        :return: True if the timezone is valid, else False
        """
        return SchedulerConfigBuilder.validated_timezone(tz) is not None

    @staticmethod
    def validated_timezone(tz):
        """
        Generic and optimized method to get a timezone from a timezone name
        :param tz: name of the timezone
        :return: timezone instance, None if it not valid
        """
        tz_lower = str(tz).lower()
        if tz_lower in SchedulerConfigBuilder._checked_timezones:
            return str(SchedulerConfigBuilder._checked_timezones[tz_lower])

        if tz_lower in SchedulerConfigBuilder._invalid_timezones:
            return None

        validated = SchedulerConfigBuilder._all_timezones.get(tz_lower, None)
        if validated is not None:
            # keep list off approved timezones to make next checks much faster
            SchedulerConfigBuilder._checked_timezones[tz_lower] = pytz.timezone(validated)
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

            # case insensitive lookup for format pytz name
            tz_str = SchedulerConfigBuilder._all_timezones.get(tz_lower)
            if tz_str is not None:
                # found it, no need to check for invalid timezone here because of lookup
                tz = pytz.timezone(tz_str)
                SchedulerConfigBuilder._checked_timezones[tz_lower] = tz
                return tz

            # not a valid timezone
            SchedulerConfigBuilder._invalid_timezones.add(tz_lower)

        raise ValueError("Timezone {} is not a valid timezone".format(tz_name))
