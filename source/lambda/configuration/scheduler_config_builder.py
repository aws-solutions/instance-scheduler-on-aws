######################################################################################################################
#  Copyright 2019 Amazon.com, Inc. or its affiliates. All Rights Reserved.                                           #
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
import boto_retry
from configuration.instance_schedule import InstanceSchedule
from configuration.running_period import RunningPeriod
from configuration.scheduler_config import SchedulerConfig
from configuration.setbuilders.month_setbuilder import MonthSetBuilder
from configuration.setbuilders.monthday_setbuilder import MonthdaySetBuilder
from configuration.setbuilders.weekday_setbuilder import WeekdaySetBuilder

REGEX_SSM_PARAM = "{param:(.+?)}"

ATTR_BEGINTIME = "begintime"
ATTR_CROSS_ACCOUNT_ROLES = "cross_account_roles"
ATTR_CREATE_RDS_SNAPSHOT = "create_rds_snapshot"
ATTR_DEFAULT_TIMEZONE = "default_timezone"
ATTR_ENDTIME = "endtime"
ATTR_ENFORCED = "enforced"
ATTR_HIBERNATE = "hibernate"
ATTR_INSTANCE_TYPE = "instancetype"
ATTR_MONTHDAYS = "monthdays"
ATTR_MONTHS = "months"
ATTR_NAME = "name"
ATTR_OVERRIDE_STATUS = "override_status"
ATTR_PERIOD = "period"
ATTR_PERIODS = "periods"
ATTR_REGIONS = "regions"
ATTR_RETAIN_RUNNING = "retain_running"
ATTR_SCHEDULE_DT = "schedule_dt"
ATTR_SCHEDULE_LAMBDA_ACCOUNT = "schedule_lambda_account"
ATTR_SCHEDULED_SERVICES = "scheduled_services"
ATTR_SCHEDULE_CLUSTERS = "schedule_clusters"
ATTR_SCHEDULES = "schedules"
ATTR_STARTED_TAGS = "started_tags"
ATTR_STOP_NEW_INSTANCES = "stop_new_instances"
ATTR_STOPPED_TAGS = "stopped_tags"
ATTR_TAGNAME = "tag_name"
ATTR_TIMEZONE = "timezone"
ATTR_TRACE = "trace"
ATTR_USE_MAINTENANCE_WINDOW = "use_maintenance_window"
ATTR_SSM_MAINTENANCE_WINDOW = "ssm_maintenance_window"
ATTR_USE_METRICS = "use_metrics"
ATTR_WEEKDAYS = "weekdays"

MSG_BEGIN_MUST_BEFORE_END = "Begin time {} must be earlier than end time in {}"
MSG_DUPLICATE_PERIOD_NAME_FOUND = "Duplicate period name \"{}\" found"
MSG_DUPLICATE_SCHEDULE_NAME_FOUND = "Duplicate schedule name \"{}\" found"
MSG_INVALID_DEFAULT_TIMEZONE = "\"{}\" is not a valid timezone, use pytz.all_timezones to list all valid zones"
MSG_INVALID_OVERRIDE_STATUS = "{} is not a valid value for {}, possible values are {}"
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
            self._ssm = boto_retry.get_client_with_retries("ssm", methods=["get_parameters"])
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
            scheduler_metrics = config.get(configuration.METRICS, False)

            cross_account_roles = self.get_cross_account_roles(config)

            return SchedulerConfig(scheduled_services=config.get(configuration.SCHEDULED_SERVICES, []) or [],
                                   schedule_clusters=config.get(configuration.SCHEDULE_CLUSTERS, False),
                                   create_rds_snapshot=config.get(configuration.CREATE_RDS_SNAPSHOT, True),
                                   tag_name=get_scheduler_tagname(config),
                                   regions=config.get(configuration.REGIONS, []) or [],
                                   default_timezone=get_default_timezone(config),
                                   schedules=self._build_schedules(config, get_default_timezone(config), scheduler_metrics,
                                                                   config_date),
                                   trace=config.get(configuration.TRACE, False),
                                   use_metrics=scheduler_metrics,
                                   cross_account_roles=cross_account_roles,
                                   schedule_lambda_account=config.get(configuration.SCHEDULE_LAMBDA_ACCOUNT, True),
                                   started_tags=config.get(configuration.STARTED_TAGS, ""),
                                   stopped_tags=config.get(configuration.STOPPED_TAGS, ""))
        except ValueError as ex:
            if self._logger is not None:
                self._logger.error(str(ex))
            return None

    def get_cross_account_roles(self, config):
        cross_account_roles = []
        for role in config.get(configuration.CROSS_ACCOUNT_ROLES, []) or []:
            if regex.match(REGEX_SSM_PARAM, role):
                names = regex.findall(REGEX_SSM_PARAM, role)
                if len(names) > 0:
                    resp = self.ssm.get_parameters_with_retries(Names=list(set(names)))
                    for p in resp.get("Parameters", []):
                        if p["Type"] == "StringList":
                            cross_account_roles += p["Value"].split(",")
                        else:
                            cross_account_roles.append(p["Value"])
            else:
                cross_account_roles.append(role)
        return cross_account_roles

    # build the schedules from the configuration
    def _build_schedules(self, conf, dflt_tz, scheduler_use_metrics, dt):
        schedules = {}

        # use the periods to build the schedules that can be assigned to the instances
        for schedule_config in conf.get(configuration.SCHEDULES, []):
            schedule = self._build_schedule(schedule_config, dflt_tz, scheduler_use_metrics, dt)
            if schedule is None:
                continue
            if schedule.name in schedules:
                if self._logger is not None:
                    self._logger.error(MSG_DUPLICATE_SCHEDULE_NAME_FOUND, schedule.name)
                continue

            schedules[schedule.name] = schedule

        return schedules

    def _build_schedule(self, schedule_config, dflt_tz, scheduler_use_config, dt):

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

        def get_override_status(config):
            if configuration.OVERWRITE in config:
                if configuration.OVERRIDE_STATUS in config:
                    raise ValueError(
                        MSG_OVERWRITE_OVERRIDE_MUTUAL_EXCLUSIVE.format(configuration.OVERWRITE, configuration.OVERRIDE_STATUS))
                overwrite = config[configuration.OVERWRITE]
                return configuration.OVERRIDE_STATUS_RUNNING if overwrite else configuration.OVERRIDE_STATUS_STOPPED
            status = config.get(configuration.OVERRIDE_STATUS, None)
            if status is not None and status not in configuration.OVERRIDE_STATUS_VALUES:
                raise ValueError(MSG_INVALID_OVERRIDE_STATUS.format(status, configuration.OVERRIDE_STATUS,
                                                                    ",".join(configuration.OVERRIDE_STATUS_VALUES)))
            return status

        try:

            timezone = get_timezone(schedule_config)
            override_status = get_override_status(schedule_config)
            periods_for_schedule = []

            # ignore periods if there is an always on or if override_status option is used
            if not override_status:
                # use current date and time for timezone of schedule
                current_schema_dt = dt.replace(tzinfo=SchedulerConfigBuilder._get_timezone(timezone))
                periods_for_schedule = self._get_schedule_periods(schedule_config, current_schema_dt)

            return InstanceSchedule(name=get_schedule_name(schedule_config),
                                    periods=periods_for_schedule,
                                    timezone=timezone,
                                    override_status=override_status,
                                    description=schedule_config.get(configuration.DESCRIPTION, ""),
                                    use_metrics=schedule_config.get(configuration.METRICS, scheduler_use_config),
                                    stop_new_instances=schedule_config.get(configuration.STOP_NEW_INSTANCES, True),
                                    use_maintenance_window=schedule_config.get(configuration.USE_MAINTENANCE_WINDOW, False),
                                    ssm_maintenance_window=schedule_config.get(configuration.SSM_MAINTENANCE_WINDOW, None),
                                    enforced=schedule_config.get(configuration.ENFORCED, False),
                                    hibernate=schedule_config.get(configuration.HIBERNATE, False),
                                    retain_running=schedule_config.get(configuration.RETAINED_RUNNING))

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
                     ATTR_SCHEDULE_CLUSTERS,
                     ATTR_CREATE_RDS_SNAPSHOT,
                     ATTR_USE_METRICS,
                     ATTR_SCHEDULE_LAMBDA_ACCOUNT,
                     ATTR_STARTED_TAGS,
                     ATTR_STOPPED_TAGS]:
            config_args[attr] = d.get(attr, None)

        for attr in [ATTR_REGIONS,
                     ATTR_CROSS_ACCOUNT_ROLES,
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
                         ATTR_OVERRIDE_STATUS,
                         ATTR_STOP_NEW_INSTANCES,
                         ATTR_USE_METRICS,
                         ATTR_ENFORCED,
                         ATTR_HIBERNATE,
                         ATTR_RETAIN_RUNNING,
                         ATTR_SSM_MAINTENANCE_WINDOW,
                         ATTR_USE_MAINTENANCE_WINDOW]:
                schedule_args[attr] = schedule_data.get(attr, None)

            for attr in [ATTR_SCHEDULE_DT]:
                if attr in schedule_data:
                    schedule_args[attr] = dateutil.parser.parse(schedule_data[attr])

            if schedule_args[ATTR_OVERRIDE_STATUS] is None:

                schedule_args[ATTR_PERIODS] = []

                for period in schedule_data.get(ATTR_PERIODS):
                    temp = period.split(configuration.INSTANCE_TYPE_SEP)
                    if len(temp) > 1:
                        name = temp[0]
                        instance_type = temp[1]
                    else:
                        name = period
                        instance_type = None
                    schedule_args[ATTR_PERIODS].append({ATTR_PERIOD: periods[name], ATTR_INSTANCE_TYPE: instance_type})

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
                     ATTR_USE_METRICS,
                     ATTR_SCHEDULE_CLUSTERS,
                     ATTR_CREATE_RDS_SNAPSHOT,
                     ATTR_SCHEDULE_LAMBDA_ACCOUNT,
                     ATTR_STARTED_TAGS,
                     ATTR_STOPPED_TAGS]:
            if attr in config.__dict__ and config.__dict__[attr] is not None:
                result[attr] = config.__dict__[attr]

        for attr in [ATTR_STARTED_TAGS,
                     ATTR_STOPPED_TAGS]:
            if attr in config.__dict__ and config.__dict__[attr] is not None:
                result[attr] = ",".join(["{}={}".format(t["Key"], t["Value"]) for t in config.__dict__[attr]])

        for attr in [ATTR_REGIONS,
                     ATTR_CROSS_ACCOUNT_ROLES,
                     ATTR_SCHEDULED_SERVICES]:
            if len(config.__dict__[attr]) > 0:
                result[attr] = list(config.__dict__[attr])

        result[ATTR_SCHEDULES] = {}
        result[ATTR_PERIODS] = {}

        for schedule_name in config.schedules:
            result[ATTR_SCHEDULES][schedule_name] = {}
            schedule = config.schedules[schedule_name]
            for attr in [ATTR_NAME,
                         ATTR_TIMEZONE,
                         ATTR_OVERRIDE_STATUS,
                         ATTR_STOP_NEW_INSTANCES,
                         ATTR_USE_METRICS,
                         ATTR_ENFORCED,
                         ATTR_HIBERNATE,
                         ATTR_USE_MAINTENANCE_WINDOW,
                         ATTR_SSM_MAINTENANCE_WINDOW,
                         ATTR_RETAIN_RUNNING]:
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
                instance_type = p[ATTR_INSTANCE_TYPE]
                result[ATTR_SCHEDULES][schedule_name][ATTR_PERIODS].append(
                    period.name + (("{}{}".format(configuration.INSTANCE_TYPE_SEP, instance_type)) if instance_type else ""))
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
