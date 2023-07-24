# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import copy
import datetime
import time
from dataclasses import dataclass, field
from typing import Any, Optional, TypedDict
from zoneinfo import ZoneInfo

from instance_scheduler import configuration
from instance_scheduler.configuration.instance_schedule import InstanceSchedule
from instance_scheduler.configuration.running_period import RunningPeriod
from instance_scheduler.util.app_env import get_app_env


class TagTemplate(TypedDict):
    Key: str
    Value: str


@dataclass(frozen=True)
class SchedulingContext:
    account_id: str
    service: str
    region: str
    current_dt: datetime.datetime
    tag_name: str
    default_timezone: ZoneInfo
    schedules: dict[str, InstanceSchedule]
    schedule_clusters: bool
    trace: bool
    enable_ssm_maintenance_windows: bool
    use_metrics: bool
    namespace: str
    aws_partition: str
    scheduler_role_name: str
    organization_id: str
    schedule_lambda_account: bool
    create_rds_snapshot: bool
    started_tags: list[TagTemplate] = field(default_factory=list)
    stopped_tags: list[TagTemplate] = field(default_factory=list)

    def get_schedule(self, name: Optional[str]) -> Optional[InstanceSchedule]:
        """
        Get a schedule by its name
        :param name: name of the schedule
        :return: Schedule, None f it does not exist
        """
        return self.schedules[name] if name in self.schedules else None

    def to_dict(self) -> dict[Any, Any]:
        """
        build a dictionary from a context instance to be passed safely in the event of a lambda function

        note - adapted from original code, much refactoring is almost certainly possible
        :param config: input SchedulerConfig
        :return: the schedule as a dict
        """
        result = {}

        # include values only if set?
        for attr in [
            "tag_name",
            "trace",
            "namespace",
            "scheduler_role_name",
            "organization_id",
            "aws_partition",
            "enable_ssm_maintenance_windows",
            "use_metrics",
            "schedule_clusters",
            "create_rds_snapshot",
            "schedule_lambda_account",
            "started_tags",
            "stopped_tags",
        ]:
            if attr in self.__dict__ and self.__dict__[attr] is not None:
                result[attr] = self.__dict__[attr]

        result["default_timezone"] = str(self.default_timezone)
        result["current_dt"] = self.current_dt.isoformat()

        for attr in ["started_tags", "stopped_tags"]:
            if attr in self.__dict__ and self.__dict__[attr] is not None:
                result[attr] = ",".join(
                    [
                        "{}={}".format(t.get("Key"), t.get("Value"))
                        for t in self.__dict__[attr]
                    ]
                )

        for attr in ["region", "account_id", "service"]:
            result[attr] = self.__dict__[attr]

        # initialize schedules/periods
        result["schedules"] = {}
        result["periods"] = {}

        # putting schedule object into list of schedules by key
        # this could be done recursively
        for schedule_name in self.schedules:
            result["schedules"][schedule_name] = {}
            schedule = self.schedules[schedule_name]
            for attr in [
                "name",
                "timezone",
                "override_status",
                "stop_new_instances",
                "use_metrics",
                "enforced",
                "hibernate",
                "use_maintenance_window",
                "ssm_maintenance_window",
                "retain_running",
            ]:
                if attr in schedule.__dict__ and schedule.__dict__[attr] is not None:
                    result["schedules"][schedule_name][attr] = schedule.__dict__[attr]

            if schedule.override_status is not None:
                continue

            result["schedules"][schedule_name]["periods"] = []

            for p in schedule.periods:
                period = p["period"]
                instance_type = p.get("instancetype", None)
                result["schedules"][schedule_name]["periods"].append(
                    period.name
                    + (
                        ("{}{}".format(configuration.INSTANCE_TYPE_SEP, instance_type))
                        if instance_type
                        else ""
                    )
                )
                if period.name in result["periods"]:
                    continue

                result["periods"][period.name] = {}
                for attr in ["begintime", "endtime"]:
                    tm = period.__dict__[attr]
                    if tm is not None:
                        result["periods"][period.name][attr] = "{:0>2d}:{:0>2d}".format(
                            tm.hour, tm.minute
                        )

                for attr in ["weekdays", "monthdays", "months"]:
                    s = period.__dict__[attr]
                    if s is None:
                        continue
                    result["periods"][period.name][attr] = list(s)
        return result


def from_dict(config_dict: dict[Any, Any]) -> SchedulingContext:
    """
    build a configuration object instance that is passed as a dictionary in the event of a lambda function
        :param config_dict: a dictionary representation of a schedule
        :return: a SchedulerConfig built from the dict
    """

    config_args = {}
    for attr in [
        "tag_name",
        "trace",
        "namespace",
        "scheduler_role_name",
        "organization_id",
        "aws_partition",
        "enable_ssm_maintenance_windows",
        "use_metrics",
        "schedule_clusters",
        "create_rds_snapshot",
        "schedule_lambda_account",
    ]:
        config_args[attr] = config_dict.get(attr, None)

    for attr in ["region", "account_id", "service"]:
        config_args[attr] = config_dict.get(attr, "")

    config_args["current_dt"] = datetime.datetime.fromisoformat(
        config_dict.get("current_dt", "")
    )
    config_args["default_timezone"] = ZoneInfo(config_dict["default_timezone"])

    for attr in ["started_tags", "stopped_tags"]:
        config_args[attr] = build_tags_from_template(config_dict.get(attr, ""))
    periods = {}

    for period_name in config_dict.get("periods", {}):
        period_data = config_dict["periods"][period_name]
        period_args = {"name": period_name}

        for attr in ["begintime", "endtime"]:
            if attr in period_data:
                period_args[attr] = get_time_from_string(period_data[attr])

        for attr in ["weekdays", "monthdays", "months"]:
            if attr in period_data:
                period_args[attr] = set(period_data.get(attr, None))

        period = RunningPeriod(**period_args)
        periods[period_name] = period

    config_args["schedules"] = {}

    for schedule_name in config_dict.get("schedules", {}):
        schedule_args = {}
        schedule_data = config_dict["schedules"][schedule_name]
        for attr in [
            "name",
            "timezone",
            "override_status",
            "stop_new_instances",
            "use_metrics",
            "enforced",
            "hibernate",
            "use_maintenance_window",
            "ssm_maintenance_window",
            "retain_running",
        ]:
            schedule_args[attr] = schedule_data.get(attr, None)

        if schedule_args["override_status"] is None:
            schedule_args["periods"] = []

            for schedule_period in schedule_data.get("periods"):
                temp = schedule_period.split(configuration.INSTANCE_TYPE_SEP)
                if len(temp) > 1:
                    name = temp[0]
                    instance_type = temp[1]
                else:
                    name = schedule_period
                    instance_type = None
                schedule_args["periods"].append(
                    {"period": periods[name], "instancetype": instance_type}
                )

        schedule = InstanceSchedule(**schedule_args)
        config_args["schedules"][schedule_name] = schedule

    config = SchedulingContext(**config_args)

    if (
        config.current_dt.tzinfo is None
        or config.current_dt.tzinfo.utcoffset(config.current_dt) is None
    ):
        raise ValueError(
            "Attempted to build scheduling_context with timezone unaware scheduling time! time received: "
            "{}".format(config_dict.get("current_dt"))
        )
    # https://docs.python.org/3/library/datetime.html#determining-if-an-object-is-aware-or-naive

    return config


def get_time_from_string(timestr: Optional[str]) -> Optional[datetime.time]:
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


def build_tags_from_template(
    tags_str: Any, tag_variables: Optional[Any] = None
) -> list[TagTemplate]:
    lastkey = None
    tags = {}
    for tag in tags_str.split(","):
        if "=" in tag:
            t = tag.partition("=")
            tags[t[0]] = t[2]
            lastkey = t[0]
        elif lastkey is not None:
            tags[lastkey] = ",".join([tags[lastkey], tag])

    tag_vars = {} if tag_variables is None else copy.copy(tag_variables)

    dt = datetime.datetime.now(datetime.timezone.utc)
    tag_vars.update(
        {
            configuration.TAG_VAL_SCHEDULER: get_app_env().stack_name,
            configuration.TAG_VAL_YEAR: "{:0>4d}".format(dt.year),
            configuration.TAG_VAL_MONTH: "{:0>2d}".format(dt.month),
            configuration.TAG_VAL_DAY: "{:0>2d}".format(dt.day),
            configuration.TAG_VAL_HOUR: "{:0>2d}".format(dt.hour),
            configuration.TAG_VAL_MINUTE: "{:0>2d}".format(dt.minute),
            configuration.TAG_VAL_TIMEZONE: "UTC",
        }
    )

    for tag in tags:
        value = tags[tag]
        if value not in ["", None]:
            for v in tag_vars:
                tags[tag] = tags[tag].replace("{{{}}}".format(v), tag_vars[v])

    return [{"Key": t, "Value": tags[t]} for t in tags]
