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

import json
import os
import re
from datetime import datetime, timedelta

import boto3
from boto3.dynamodb.conditions import Key

import configuration
from boto_retry import add_retry_methods_to_resource
from configuration.config_dynamodb_adapter import ConfigDynamodbAdapter
from configuration.instance_schedule import InstanceSchedule
from configuration.scheduler_config_builder import SchedulerConfigBuilder
from configuration.setbuilders.month_setbuilder import MonthSetBuilder
from configuration.setbuilders.monthday_setbuilder import MonthdaySetBuilder
from configuration.setbuilders.weekday_setbuilder import WeekdaySetBuilder
from util.named_tuple_builder import as_namedtuple

ERR_PERIOD_BEGIN_LATER_THAN_END = "error: period begintime {} can not be later than endtime {}"
ERR_SCHEDULE_INVALID_OVERRIDE = "{} is not a valid value for {}, possible values are {}"
ERR_SCHEDULE_OVERWRITE_OVERRIDE_EXCLUSIVE = "{} option is mutually exclusive with {} option"
ERR_CREATE_PERIOD_EXISTS = "error: period {} already exists"
ERR_CREATE_SCHEDULE_EXISTS = "error: schedule {} already exists"
ERR_DEL_PERIOD_EMPTY = "error: period name parameter can not be empty"
ERR_DEL_PERIOD_IN_USE = "error: period {} can not be deleted because it is still used in schedule(s) {}"
ERR_DEL_PERIOD_NOT_FOUND = "not found: period {} does not exist"
ERR_DEL_SCHEDULE_NAME_EMPTY = "error: schedule name parameter can not be empty"
ERR_DEL_SCHEDULE_NOT_FOUND = "not found: schedule {} does not exist"
ERR_GET_EMPTY_PERIOD_NAME = "error: period name parameter can not be empty"
ERR_GET_PERIOD_NOT_FOUND = "not found: period {} does not exist"
ERR_GET_SCHEDULE_NAME_EMPTY = "error: error schedule name parameter can not be empty"
ERR_GET_SCHEDULE_NOT_FOUND = "not found: schedule {} does not exist"
ERR_GET_USAGE_INVALID_END_DATE = "error: invalid enddate {}, must be a valid date in format yyyymmdd {}"
ERR_GET_USAGE_INVALID_START_DATE = "error: invalid startdate {}, must be a valid date in format yyyymmdd {}"
ERR_GET_USAGE_SCHEDULE_NAME_EMPTY = "error: error schedule name parameter can not be empty"
ERR_GET_USAGE_SCHEDULE_NOT_FOUND = "not found: schedule {} does not exist"
ERR_GET_USAGE_START_MUST_BE_LESS_OR_EQUAL_STOP = "stop_date must be equal or later than start_date"
ERR_NAME_PARAM_MISSING = "error: name parameter is missing"
ERR_NO_PERIODS = "error: at least one period condition must be specified"
ERR_PERIOD_INVALID_MONTHDAYS = "error: {} is not a valid month days specification"
ERR_PERIOD_INVALID_MONTHS = "error: {} is not a valid months specification"
ERR_PERIOD_INVALID_TIME = "error: {} {} is not a valid time"
ERR_PERIOD_INVALID_WEEKDAYS = "error: {} is not a valid weekdays specification {}"
ERR_PERIOD_UNKNOWN_PARAMETER = "error: {} is not a valid parameter, valid parameters are {}"
ERR_SCHEDULE_INVALID_BOOLEAN = "error: {} for parameter {} is not a valid boolean value"
ERR_SCHEDULE_INVALID_TIMEZONE = "error: {} is not a valid time zone for parameter {}"
ERR_SCHEDULE_NAME_MISSING = "error: name parameter is missing"
ERR_SCHEDULE_NO_PERIOD = "error: at least one period must be specified for a schedule"
ERR_SCHEDULE_PERIOD_DOES_NOT_EXISTS = "error: not found: period {} does not exist"
ERR_SCHEDULE_UNKNOWN_PARAMETER = "error: {} is not a valid parameter, valid parameters are {}"
ERR_UPDATE_INVALID_BOOL_PARAM = "error: {} for parameter {} is not a valid boolean value"
ERR_UPDATE_INVALID_TZ_PARAMETER = "error: {} is not a valid time zone for parameter {}"
ERR_UPDATE_PERIOD_NAME_EMPTY = "error: period name parameter can not be empty"
ERR_UPDATE_PERIOD_NOT_FOUND = "not found: period {} does not exist"
ERR_UPDATE_SCHEDULE_NAME_EMPTY = "error: schedule name parameter can not be empty"
ERR_UPDATE_SCHEDULE_NOT_FOUND = "not found: schedule {} does not exist"
ERR_UPDATE_TAGNAME_EMPTY = "error: tagname parameter must be specified"
ERR_UPDATE_UNKNOWN_PARAMETER = "error: {} is not a valid parameter"
ERR_UPDATE_UNKNOWN_SERVICE = "{} is not a supported service"
ERR_STOP_MUST_BE_LATER_OR_EQUAL_TO_START = "stop_date must be equal or later than start_date"

INF_ADD_ACCOUNT_EVENT_PERMISSION = "Add permission for account {} to put events on message bus, sid is {}"
INF_REMOVE_EVENT_PERMISSION = "Remove permission for account {} to put events on event bus, sid = {}"


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

        def default(self, o):
            if isinstance(o, set):
                return list(o)
            if isinstance(o, datetime):
                return o.replace(second=0).strftime("%x %X")

            return json.JSONEncoder.default(self, o)

    def __init__(self, logger, context):
        """
        Initializes the config API
        :param logger: logger for the admin api
        :param context: Lambda context
        """
        self._table_name = self.table_name
        self._table = boto3.resource("dynamodb").Table(self._table_name)
        add_retry_methods_to_resource(self._table, ["scan", "get_item", "put_item", "delete_item"], context=context)
        self._configuration = None
        self._logger = logger
        self._context = context

    @property
    def configuration(self):
        """
        Returns and cached configuration
        :return: scheduler configuration
        """
        if self._configuration is None:
            configdata = ConfigDynamodbAdapter(self._table.name).config
            self._configuration = SchedulerConfigBuilder(logger=self._logger).build(configdata)
        return self._configuration

    @property
    def table_name(self):
        """
        Returns the name of the config table
        :return: name of the config
        """
        return os.getenv(configuration.ENV_CONFIG)

    def get_config_as_json(self):
        """
        Gets the configuration as json
        :return:
        """
        resp = self._table.get_item_with_rerties(Key={"name": "scheduler", "type": "config"}, ConsistentRead=True)
        item = resp.get("Item", {})
        return self._for_output(item)

    def update_config(self, **settings):
        """
        Updates configuration, validates new values
        :param settings: settings values
        :return: updated values
        """
        valid_attributes = [configuration.METRICS,
                            configuration.CROSS_ACCOUNT_ROLES,
                            configuration.DEFAULT_TIMEZONE,
                            configuration.REGIONS,
                            configuration.SCHEDULE_LAMBDA_ACCOUNT,
                            configuration.TAGNAME,
                            configuration.TRACE,
                            ConfigAdmin.TYPE_ATTR,
                            configuration.SCHEDULED_SERVICES,
                            configuration.SCHEDULE_CLUSTERS,
                            configuration.CREATE_RDS_SNAPSHOT,
                            configuration.STARTED_TAGS,
                            configuration.STOPPED_TAGS]

        checked_settings = {}

        for attr in settings:

            if attr in [ConfigAdmin.TYPE_ATTR, configuration.NAME]:
                continue

            # only valid fields
            if attr not in valid_attributes:
                raise ValueError(ERR_UPDATE_UNKNOWN_PARAMETER.format(attr))

            # remove None fields
            if settings[attr] is None:
                continue

            # remove empty strings
            if len(str(settings[attr])) == 0:
                continue

            # make sure these fields are set as sets
            if attr in [configuration.REGIONS, configuration.CROSS_ACCOUNT_ROLES, configuration.SCHEDULED_SERVICES]:
                temp = self._ensure_set(settings[attr])
                if len(settings[attr]) > 0:
                    checked_settings[attr] = temp

                continue

            # make sure these fields are valid booleans
            if attr in [configuration.METRICS,
                        configuration.TRACE,
                        configuration.SCHEDULE_LAMBDA_ACCOUNT,
                        configuration.CREATE_RDS_SNAPSHOT,
                        configuration.SCHEDULE_CLUSTERS]:
                bool_value = self._ensure_bool(settings[attr])
                if bool_value is None:
                    raise ValueError(ERR_UPDATE_INVALID_BOOL_PARAM.format(settings[attr], attr))
                checked_settings[attr] = bool_value
                continue

            # validate timezone
            if attr == configuration.DEFAULT_TIMEZONE:
                default_tz = settings[configuration.DEFAULT_TIMEZONE]
                if not SchedulerConfigBuilder.is_valid_timezone(default_tz):
                    raise ValueError(
                        ERR_UPDATE_INVALID_TZ_PARAMETER.format(default_tz, configuration.DEFAULT_TIMEZONE))
                checked_settings[attr] = default_tz
                continue

            checked_settings[attr] = settings[attr]

            if configuration.TAGNAME not in settings:
                raise ValueError(ERR_UPDATE_TAGNAME_EMPTY)

            for service in settings.get(configuration.SCHEDULED_SERVICES, []):
                if service not in ConfigAdmin.SUPPORTED_SERVICES:
                    raise ValueError(ERR_UPDATE_UNKNOWN_SERVICE.format(service))

        # keys for config item
        checked_settings[ConfigAdmin.TYPE_ATTR] = "config"
        checked_settings[configuration.NAME] = "scheduler"

        self._table.put_item_with_retries(Item=checked_settings)

        return ConfigAdmin._for_output(checked_settings)

    def list_periods(self):
        """
        Lists all periods
        :return: all configured periods
        """
        periods = self._list_periods()
        for period in periods:
            ConfigAdmin._for_output(period)
        return {"periods": ConfigAdmin._for_output(periods)}

    def get_period(self, name, exception_if_not_exists=True):
        """
        Gets a specific period
        :param name: name of the period
        :param exception_if_not_exists: set to True to raise an exception if it does not exist
        :return:
        """
        if name is None or len(name) == 0:
            raise ValueError(ERR_GET_EMPTY_PERIOD_NAME)
        period = self._get_period(name)
        if period is None:
            if exception_if_not_exists:
                raise ValueError(ERR_GET_PERIOD_NOT_FOUND.format(name))
            return None
        return {"period": ConfigAdmin._for_output(period)}

    def create_period(self, **kwargs):
        """
        Creates a new period
        :param kwargs: period parameters, see validate_period for allowed parameters
        :return: Validated and created period
        """
        period = self._validate_period(**kwargs)
        name = period[configuration.NAME]
        if self._get_period(name) is not None:
            raise ValueError(ERR_CREATE_PERIOD_EXISTS.format(name))
        self._table.put_item_with_retries(Item=period)
        return {"period": ConfigAdmin._for_output(period)}

    def update_period(self, **kwargs):
        """
        Updates an existing period
        :param kwargs:  period data, see validate_period for allowed parameters
        :return: validated and updated period
        """
        period = self._validate_period(**kwargs)
        name = period[configuration.NAME]
        if name is None or len(name) == 0:
            raise ValueError(ERR_UPDATE_PERIOD_NAME_EMPTY)
        if self._get_period(name) is None:
            raise ValueError(ERR_UPDATE_PERIOD_NOT_FOUND.format(name))
        self._table.put_item_with_retries(Item=period)
        return {"period": ConfigAdmin._for_output(period)}

    def delete_period(self, name, exception_if_not_exists=False):
        """
        Deletes a period. Note that a period can ony be deleted when not longer used in any schedule
        :param name: Name of the period
        :param exception_if_not_exists: Set to true is an exception should be raised if the period did not exist
        :return:
        """
        if name is None or len(name) == 0:
            raise ValueError(ERR_DEL_PERIOD_EMPTY)

        # test if period is used in any schedule
        schedules_using_period = []
        for s in self._list_schedules():
            for p in s.get(configuration.PERIODS, []):
                # period can be a combination of name and instance type
                if p.split(configuration.INSTANCE_TYPE_SEP)[0] == name:
                    schedules_using_period.append(s[configuration.NAME])

        if len(schedules_using_period) > 0:
            raise ValueError(ERR_DEL_PERIOD_IN_USE.format(name, ", ".join(schedules_using_period)))

        if self._get_period(name) is not None:
            self._table.delete_item_with_retries(Key={"name": name, "type": "period"})
            return {"period": name}
        else:
            if exception_if_not_exists:
                raise ValueError(ERR_DEL_PERIOD_NOT_FOUND.format(name))
            return None

    def list_schedules(self):
        """
        List all configured schedules
        :return: all schedules
        """
        schedules = self._list_schedules()
        return {"schedules": ConfigAdmin._for_output(schedules)}

    def get_schedule(self, name, exception_if_not_exists=True):
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
                raise ValueError(ERR_GET_SCHEDULE_NOT_FOUND.format(name))
            return None
        return {"schedule": ConfigAdmin._for_output(schedule)}

    def create_schedule(self, **kwargs):
        """
        Creates a new schedule
        :param kwargs: schedule data, see validate_schedule for allowed parameters
        :return: Validated data of created schedule
        """
        schedule = self._validate_schedule(**kwargs)
        name = schedule[configuration.NAME]
        if self._get_schedule(name) is not None:
            raise ValueError(ERR_CREATE_SCHEDULE_EXISTS.format(name))
        self._table.put_item_with_retries(Item=schedule)
        return {"schedule": ConfigAdmin._for_output(schedule)}

    def update_schedule(self, **kwargs):
        """
        Updates an existing schedule
        :param kwargs: schedule data, see validate_schedule for allowed parameters
        :return: Validated updated schedule
        """
        schedule = self._validate_schedule(**kwargs)
        name = schedule[configuration.NAME]
        if name is None or len(name) == 0:
            raise ValueError(ERR_UPDATE_SCHEDULE_NAME_EMPTY)
        if self._get_schedule(name) is None:
            raise ValueError(ERR_UPDATE_SCHEDULE_NOT_FOUND.format(name))
        self._table.put_item_with_retries(Item=schedule)
        return {"schedule": ConfigAdmin._for_output(schedule)}

    def delete_schedule(self, name, exception_if_not_exists=True):
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
                raise ValueError(ERR_DEL_SCHEDULE_NOT_FOUND.format(name))
            return None
        self._table.delete_item_with_retries(Key={"name": name, "type": "schedule"})
        return {"schedule": name}

    def get_schedule_usage(self, name, startdate=None, enddate=None):
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
        if startdate:
            if not isinstance(startdate, datetime):
                try:
                    start = datetime.strptime(startdate, "%Y%m%d")
                except ValueError as ex:
                    raise ValueError(
                        ERR_GET_USAGE_INVALID_START_DATE.format(startdate, str(ex)))
            else:
                start = startdate
        else:
            start = startdate or datetime.now()

        if enddate:
            if not isinstance(enddate, datetime):
                try:
                    end = datetime.strptime(enddate, "%Y%m%d")
                except ValueError as ex:
                    raise ValueError(
                        ERR_GET_USAGE_INVALID_END_DATE.format(enddate, str(ex)))
            else:
                end = enddate
        else:
            end = start

        if start > end:
            raise ValueError(ERR_GET_USAGE_START_MUST_BE_LESS_OR_EQUAL_STOP)

        schedule = self.configuration.get_schedule(name)
        if schedule is None:
            raise ValueError(ERR_GET_USAGE_SCHEDULE_NOT_FOUND.format(name))
        periods = self.calculate_schedule_usage_for_period(name, start_dt=start, stop_dt=end)

        # to json and back again using custom encoder to convert datetimes
        return ConfigAdmin._for_output(periods)

    @staticmethod
    def _for_output(item):
        # to anf from json using custom encoder to convert datetime and set type data into string and lists
        return json.loads(json.dumps(item, cls=ConfigAdmin.CustomEncoder))

    @staticmethod
    def _ensure_set(s):
        if isinstance(s, list):
            return set(s)
        if isinstance(s, str):
            return set(s.split(","))
        return s

    @staticmethod
    def _set_as_list(s):
        if isinstance(s, set):
            return list(s)
        return s

    @staticmethod
    def _ensure_bool(b):
        s = str(b).lower()
        if s == "true":
            return True
        if s == "false":
            return False
        return None

    def _validate_period(self, **period):

        result = {}

        def is_valid_time(s):
            return re.match(ConfigAdmin.TIME_REGEX, s) is not None

        # allowed and validated parameters
        valid_parameters = [configuration.BEGINTIME,
                            configuration.ENDTIME,
                            configuration.WEEKDAYS,
                            configuration.MONTHDAYS,
                            configuration.MONTHS,
                            configuration.NAME,
                            configuration.DESCRIPTION]

        for attr in period:
            # indicates type for config entry
            if attr == ConfigAdmin.TYPE_ATTR:
                continue

            # parameter is allowed?
            if attr not in valid_parameters:
                raise ValueError(ERR_PERIOD_UNKNOWN_PARAMETER.format(attr, str(valid_parameters)))

            # remove None values
            if period[attr] is None or len(str(period[attr])) == 0:
                continue

            # period name
            if attr == configuration.NAME:
                result[attr] = period[attr]
                continue

            # description
            if attr == configuration.DESCRIPTION:
                result[attr] = period[attr]
                continue

            # validate start and end types times
            if attr in [configuration.BEGINTIME, configuration.ENDTIME]:
                time_str = period[attr]
                if not is_valid_time(time_str):
                    raise ValueError(ERR_PERIOD_INVALID_TIME.format(attr, time_str))
                result[attr] = str(datetime.strptime(time_str, configuration.TIME_FORMAT_STRING).time())[
                               0:len(configuration.TIME_FORMAT_STRING)]
                if configuration.BEGINTIME in result and configuration.ENDTIME in result:
                    begintime = datetime.strptime(result[configuration.BEGINTIME], configuration.TIME_FORMAT_STRING).time()
                    endtime = datetime.strptime(result[configuration.ENDTIME], configuration.TIME_FORMAT_STRING).time()
                    if begintime > endtime:
                        raise ValueError(
                            ERR_PERIOD_BEGIN_LATER_THAN_END.format(result[configuration.BEGINTIME], result[configuration.ENDTIME]))

                continue

            # check weekdays, monthdays and month sets
            if attr in [configuration.WEEKDAYS, configuration.MONTHDAYS, configuration.MONTHS]:
                temp = self._ensure_set(period[attr])

                if len(temp) == 0:
                    continue

                # validate month
                if attr == configuration.MONTHS:
                    # noinspection PyPep8
                    try:
                        MonthSetBuilder().build(temp)
                        result[attr] = temp
                        continue
                    except:
                        raise ValueError(ERR_PERIOD_INVALID_MONTHS.format(str(period[attr])))

                # validate weekdays
                if attr == configuration.WEEKDAYS:
                    try:
                        wdb = WeekdaySetBuilder(year=2016, month=12, day=31)
                        wdb.build(temp)
                        result[attr] = temp
                        continue
                    except Exception as ex:
                        raise ValueError(ERR_PERIOD_INVALID_WEEKDAYS.format(str(period[attr]), ex))

                # validate monthdays
                if attr == configuration.MONTHDAYS:
                    # noinspection PyPep8
                    try:
                        MonthdaySetBuilder(year=2016, month=12).build(temp)
                        result[attr] = temp
                        continue
                    except:
                        raise ValueError(ERR_PERIOD_INVALID_MONTHDAYS.format(str(period[attr])))

        if configuration.NAME not in result:
            raise ValueError(ERR_NAME_PARAM_MISSING)

        for condition in [configuration.BEGINTIME,
                          configuration.ENDTIME,
                          configuration.WEEKDAYS,
                          configuration.MONTHS,
                          configuration.MONTHDAYS]:
            if condition in result:
                break
        else:
            raise ValueError(ERR_NO_PERIODS)

        result[ConfigAdmin.TYPE_ATTR] = configuration.PERIOD

        return result

    # check schedule before writing it to the database
    def _validate_schedule(self, **schedule):

        result = {}

        # allowed parameters
        valid_parameters = [configuration.TIMEZONE,
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
                            configuration.SCHEDULE_CONFIG_STACK]

        for attr in schedule:

            if attr == ConfigAdmin.TYPE_ATTR:
                continue

            if attr not in valid_parameters:
                raise ValueError(ERR_SCHEDULE_UNKNOWN_PARAMETER.format(attr, valid_parameters))

            # skip None values
            if schedule[attr] is None or len(str(schedule[attr])) == 0:
                continue

            # check periods set
            if attr == configuration.PERIODS:
                temp = self._ensure_set(schedule[attr])
                if len(temp) > 0:
                    result[attr] = temp
                continue

            if attr in [configuration.NAME, configuration.SSM_MAINTENANCE_WINDOW]:
                result[attr] = schedule[attr]
                continue

            # make sure these fields are valid booleans
            if attr in [configuration.METRICS,
                        configuration.STOP_NEW_INSTANCES,
                        configuration.USE_MAINTENANCE_WINDOW,
                        configuration.RETAINED_RUNNING,
                        configuration.HIBERNATE,
                        configuration.ENFORCED]:
                bool_value = self._ensure_bool(schedule[attr])
                if bool_value is None:
                    raise ValueError(ERR_SCHEDULE_INVALID_BOOLEAN.format(schedule[attr], attr))
                result[attr] = bool_value
                continue

            # overwrite status, now deprecated, use PROP_OVERRIDE_STATUS instead
            if attr == configuration.OVERWRITE:

                if configuration.OVERRIDE_STATUS in schedule:
                    raise ValueError(
                        ERR_SCHEDULE_OVERWRITE_OVERRIDE_EXCLUSIVE.format(configuration.OVERWRITE, configuration.OVERRIDE_STATUS))

                bool_value = self._ensure_bool(schedule[attr])
                if bool_value is None:
                    raise ValueError(ERR_SCHEDULE_INVALID_BOOLEAN.format(schedule[attr], attr))
                result[
                    configuration.OVERRIDE_STATUS] = configuration.OVERRIDE_STATUS_RUNNING if bool_value \
                    else configuration.OVERRIDE_STATUS_STOPPED
                continue

            if attr == configuration.OVERRIDE_STATUS:

                if configuration.OVERWRITE in schedule:
                    raise ValueError(
                        ERR_SCHEDULE_OVERWRITE_OVERRIDE_EXCLUSIVE.format(configuration.OVERWRITE, configuration.OVERRIDE_STATUS))
                if schedule[attr] not in configuration.OVERRIDE_STATUS_VALUES:
                    raise ValueError(
                        ERR_SCHEDULE_INVALID_OVERRIDE.format(schedule[attr], attr, ",".join(configuration.OVERRIDE_STATUS_VALUES)))
                result[attr] = schedule[attr]
                continue

            # description
            if attr in [configuration.DESCRIPTION, configuration.SCHEDULE_CONFIG_STACK]:
                result[attr] = schedule[attr]
                continue

            # validate timezone
            if attr == configuration.TIMEZONE:
                timezone = schedule[configuration.TIMEZONE]
                if not SchedulerConfigBuilder.is_valid_timezone(timezone):
                    raise ValueError(
                        ERR_SCHEDULE_INVALID_TIMEZONE.format(timezone, configuration.TIMEZONE))
                result[attr] = timezone

        # name is mandatory
        if configuration.NAME not in result:
            raise ValueError(ERR_SCHEDULE_NAME_MISSING)

        # if there is no overwrite there must be at least one period
        if configuration.OVERRIDE_STATUS not in schedule:
            if configuration.PERIODS not in schedule or len(schedule[configuration.PERIODS]) == 0:
                raise ValueError(ERR_SCHEDULE_NO_PERIOD)

        # validate if periods are in configuration
        if configuration.PERIODS in result:
            # get list of all configured periods
            periods = [p[configuration.NAME] for p in self._list_periods()]
            for period in result[configuration.PERIODS]:
                if period.split(configuration.INSTANCE_TYPE_SEP)[0] not in periods:
                    raise ValueError(ERR_SCHEDULE_PERIOD_DOES_NOT_EXISTS.format(period))

        # indicates this s a schedule
        result[ConfigAdmin.TYPE_ATTR] = "schedule"

        return result

    def _items_of_type(self, config_type):

        result = []

        args = {
            "FilterExpression": Key("type").eq(config_type),
            "ConsistentRead": True
        }

        while True:
            resp = self._table.scan_with_retries(**args)
            result += resp.get("Items", [])
            if "LastEvaluatedKey" in resp:
                args["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
            else:
                break

        return result

    def _list_schedules(self):
        return self._items_of_type("schedule")

    def _list_periods(self):
        return self._items_of_type("period")

    def _get_schedule(self, schedule_name):
        resp = self._table.get_item_with_retries(Key={"name": schedule_name, "type": "schedule"}, ConsistentRead=True)
        return resp.get("Item", None)

    def _get_period(self, period_name):
        resp = self._table.get_item_with_retries(Key={"name": period_name, "type": "period"}, ConsistentRead=True)
        return resp.get("Item", None)

    def calculate_schedule_usage_for_period(self, schedule_name, start_dt, stop_dt=None, logger=None):

        result = {}

        def running_seconds(startdt, stopdt):
            return max(int((stopdt - startdt).total_seconds()), 60)

        def running_hours(startdt, stopdt):
            return int(((stopdt - startdt).total_seconds() - 1) / 3600) + 1

        def make_period(started_dt, stopped_dt):
            running_period = ({
                "begin": started_dt,
                "end": stopped_dt,
                "billing_hours": running_hours(started_dt, stopped_dt),
                "billing_seconds": running_seconds(started_dt, stopped_dt)
            })
            return running_period

        self._logger = logger

        stop = stop_dt or start_dt
        if start_dt > stop:
            raise ValueError(ERR_STOP_MUST_BE_LATER_OR_EQUAL_TO_START)

        dt = start_dt if isinstance(start_dt, datetime) else datetime(start_dt.year, start_dt.month, start_dt.day)

        config_data = ConfigDynamodbAdapter(self._table.name).config

        while dt <= stop:

            self._configuration = SchedulerConfigBuilder(logger=self._logger).build(config_data)
            conf = configuration.SchedulerConfigBuilder(self._logger).build(config=config_data, dt=dt)
            schedule = conf.get_schedule(schedule_name)

            timeline = {dt.replace(hour=0, minute=0)}
            for p in schedule.periods:
                begintime = p["period"].begintime
                endtime = p["period"].endtime
                if begintime is None and endtime is None:
                    timeline.add(dt.replace(hour=0, minute=0))
                    timeline.add(dt.replace(hour=23, minute=59))
                else:
                    if begintime:
                        timeline.add(dt.replace(hour=begintime.hour, minute=begintime.minute))
                    if endtime:
                        timeline.add(dt.replace(hour=endtime.hour, minute=endtime.minute))

            running_periods = {}
            started = None
            starting_period = None
            current_state = None
            inst = as_namedtuple("Instance", {"instance_str": "instance", "allow_resize": False})
            for tm in sorted(list(timeline)):
                desired_state, instance_type, period = schedule.get_desired_state(inst, self._logger, tm, False)

                if current_state != desired_state:
                    if desired_state == InstanceSchedule.STATE_RUNNING:
                        started = tm
                        current_state = InstanceSchedule.STATE_RUNNING
                        starting_period = period
                    elif desired_state == InstanceSchedule.STATE_STOPPED:
                        stopped = tm
                        desired_state_with_adj_check, _, __ = schedule.get_desired_state(inst, self._logger, tm, True)
                        if desired_state_with_adj_check == InstanceSchedule.STATE_RUNNING:
                            stopped += timedelta(minutes=1)
                        if current_state == InstanceSchedule.STATE_RUNNING:
                            current_state = InstanceSchedule.STATE_STOPPED
                            running_periods[starting_period] = (make_period(started, stopped))

            if current_state == InstanceSchedule.STATE_RUNNING:
                stopped = dt.replace(hour=23, minute=59) + timedelta(minutes=1)
                running_periods[starting_period] = (make_period(started, stopped))

            result[str(dt.date())] = {
                "running_periods": running_periods,
                "billing_seconds": sum([running_periods[ps]["billing_seconds"] for ps in running_periods]),
                "billing_hours": sum([running_periods[ph]["billing_hours"] for ph in running_periods])
            }

            dt += timedelta(days=1)

        return {"schedule": schedule_name, "usage": result}
