# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Optional, TypedDict, TypeGuard

from instance_scheduler import configuration
from instance_scheduler.configuration.config_admin import (
    ConfigAdmin,
    ConfigTablePeriodItem,
)
from instance_scheduler.util import safe_json
from instance_scheduler.util.app_env import get_app_env
from instance_scheduler.util.custom_resource import (
    CustomResource,
    CustomResourceRequest,
)
from instance_scheduler.util.logger import Logger

if TYPE_CHECKING:
    from aws_lambda_powertools.utilities.typing import LambdaContext
else:
    LambdaContext = object

INF_DELETE_SCHEDULE = "Deleted schedule {}"
INF_DELETED_PERIOD = "Deleted period {}"
INF_PERIOD_CREATED = "Created period {}"
INF_PERIOD_NAME = "Creating period {}"
INF_SCHEDULE_CREATED = "Created schedule {}"
INF_SCHEDULE_NAME = "Creating schedule {}"

ERR_INVALID_SCHEDULE_PROPERTY = (
    "{} is not a valid property for a schedule, valid schedule properties are {}"
)
ERR_INVALID_PERIOD_PROPERTY = (
    "{} is not a valid property for a schedule period, valid period properties are {}"
)

PERIOD_DESCRIPTION = "Schedule {} period {}, do not delete or update manually"
PERIOD_NAME = "{}-period-{:0>4d}"

PROP_BEGIN_TIME = "BeginTime"
PROP_DESCRIPTION = "Description"
PROP_END_TIME = "EndTime"
PROP_ENFORCED = "Enforced"
PROP_HIBERNATE = "Hibernate"
PROP_RETAIN_RUNNING = "RetainRunning"
PROP_INSTANCE_TYPE = "InstanceType"
PROP_METRICS = "Metrics"
PROP_MONTH_DAYS = "MonthDays"
PROP_MONTHS = "Months"
PROP_NAME = "Name"
PROP_OVERRIDE_STATUS = "OverrideStatus"
PROP_OVERWRITE = "Overwrite"
PROP_PERIODS = "Periods"
PROP_STACK_NAME = "SchedulerStack"
PROP_NO_STACK_PREFIX = "NoStackPrefix"
PROP_STOP_NEW = "StopNewInstances"
PROP_TIMEZONE = "Timezone"
PROP_USE_MAINTENANCE_WINDOW = "UseMaintenanceWindow"
PROP_SSM_MAINTENANCE_WINDOW = "SsmMaintenanceWindow"
PROP_WEEKDAYS = "WeekDays"

VALID_SCHEDULE_PROPERTIES = [
    PROP_DESCRIPTION,
    PROP_ENFORCED,
    PROP_RETAIN_RUNNING,
    PROP_METRICS,
    PROP_NAME,
    PROP_OVERWRITE,
    PROP_PERIODS,
    PROP_STOP_NEW,
    PROP_TIMEZONE,
    PROP_USE_MAINTENANCE_WINDOW,
    PROP_SSM_MAINTENANCE_WINDOW,
    PROP_NO_STACK_PREFIX,
    PROP_HIBERNATE,
    "ServiceToken",
    # these values used to be part of the sample template in the IG, but have been removed 7/23,
    # customers may still have old templates that include them property, so we need to not break compatibility
    "Timeout",
    PROP_OVERRIDE_STATUS,
]

VALID_PERIOD_PROPERTIES = [
    PROP_BEGIN_TIME,
    PROP_DESCRIPTION,
    PROP_END_TIME,
    PROP_INSTANCE_TYPE,
    PROP_MONTH_DAYS,
    PROP_MONTHS,
    PROP_WEEKDAYS,
]

LOG_STREAM = "{}-{:0>4d}{:0>2d}{:0>2d}"


class CfnSchedulePeriodProperties(TypedDict, total=False):
    Description: Optional[str]
    BeginTime: Optional[str]
    EndTime: Optional[str]
    InstanceType: Optional[str]
    MonthDays: Optional[str]
    Months: Optional[str]
    WeekDays: Optional[str]


class CfnScheduleResourceProperties(TypedDict, total=False):
    ServiceToken: str
    NoStackPrefix: Optional[str]
    Name: Optional[str]
    Description: Optional[str]
    Timezone: Optional[str]
    Enforced: Optional[str]
    Hibernate: Optional[str]
    RetainRunning: Optional[str]
    StopNewInstances: Optional[str]
    UseMaintenanceWindow: Optional[str]
    SsmMaintenanceWindow: Optional[str]
    Periods: list[CfnSchedulePeriodProperties]


class CfnScheduleHandler(CustomResource[CfnScheduleResourceProperties]):
    """
    Implements custom resource handler for CFN support for schedules/periods
    """

    def __init__(
        self,
        event: CustomResourceRequest[CfnScheduleResourceProperties],
        context: LambdaContext,
    ) -> None:
        """
        Initializes instance
        :param event: CFN event
        :param context: Lambda context
        """
        CustomResource.__init__(self, event, context)
        self.number_of_periods = 0

        app_env = get_app_env()
        classname = self.__class__.__name__
        dt = datetime.now(timezone.utc)
        log_stream = LOG_STREAM.format(classname, dt.year, dt.month, dt.day)
        self._logger = Logger(
            log_group=app_env.log_group,
            log_stream=log_stream,
            topic_arn=app_env.topic_arn,
            debug=app_env.enable_debug_logging,
        )

        self._admin = ConfigAdmin(logger=self._logger, context=context)

    @staticmethod
    def is_handling_request(
        event: Mapping[str, Any]
    ) -> TypeGuard[CustomResourceRequest[CfnScheduleResourceProperties]]:
        """
        Tests if this handler handles the event
        :param event: Tested event
        :return: True if this is custom resource event for configuring schedule/periods
        """
        return (
            event.get("StackId") is not None
            and event.get("ResourceType") == "Custom::ServiceInstanceSchedule"
        )

    @classmethod
    def _set_if_specified(
        cls,
        source: Any,
        source_name: Any,
        dest: Any,
        dest_name: Any = None,
        default: Any = None,
    ) -> None:
        val = source.get(source_name, default)
        if val is not None:
            dest[dest_name if dest_name is not None else source_name] = val

    @property
    def _schedule_resource_name(self) -> Any:
        name = self.resource_properties.get(PROP_NAME, None)
        if name is None:
            name = self.logical_resource_id
        if (
            str(self.resource_properties.get(PROP_NO_STACK_PREFIX, "False")).lower()
            == "true"
        ):
            return name
        return "{}-{}".format(self.stack_name, name)

    def _create_period(self, period: Any) -> tuple[str, Any]:
        self.number_of_periods += 1

        period_name = PERIOD_NAME.format(
            self._schedule_resource_name, self.number_of_periods
        )
        self._logger.info(INF_PERIOD_NAME, period_name)

        for p in period:
            if p not in VALID_PERIOD_PROPERTIES:
                raise ValueError(
                    ERR_INVALID_PERIOD_PROPERTY.format(
                        p, ", ".join(VALID_PERIOD_PROPERTIES)
                    )
                )

        create_period_args: ConfigTablePeriodItem = {"name": period_name}

        self._set_if_specified(
            period, PROP_BEGIN_TIME, create_period_args, configuration.BEGINTIME
        )
        self._set_if_specified(
            period, PROP_END_TIME, create_period_args, configuration.ENDTIME
        )
        self._set_if_specified(
            period, PROP_MONTH_DAYS, create_period_args, configuration.MONTHDAYS
        )
        self._set_if_specified(
            period, PROP_MONTHS, create_period_args, configuration.MONTHS
        )
        self._set_if_specified(
            period, PROP_WEEKDAYS, create_period_args, configuration.WEEKDAYS
        )

        create_period_args["description"] = PERIOD_DESCRIPTION.format(
            self._schedule_resource_name, self.number_of_periods
        )
        description_config = period.get(PROP_DESCRIPTION, None)
        if description_config is not None:
            create_period_args["description"] = "{}, {}".format(
                description_config, create_period_args["description"]
            )

        instance_type = period.get(PROP_INSTANCE_TYPE, None)
        period = self._admin.create_period(create_period_args)

        self._logger.info(INF_PERIOD_CREATED, safe_json(period, 3))

        return period_name, instance_type

    def _delete_periods(self) -> None:
        i = 0
        while True:
            i += 1
            name = PERIOD_NAME.format(self._schedule_resource_name, i)
            period = self._admin.delete_period(name, exception_if_not_exists=False)
            if period is None:
                break
            else:
                self._logger.info(INF_DELETED_PERIOD, name)

    def _create_schedule(self) -> None:
        self._logger.info(INF_SCHEDULE_NAME, self._schedule_resource_name)

        create_schedule_args = {configuration.NAME: self._schedule_resource_name}

        ps = self.resource_properties

        for pr in ps:
            # fix for typo in older release, fix parameter if old version with typo is used for compatibility
            if pr == "UseMaintenaceWindow":
                pr = PROP_USE_MAINTENANCE_WINDOW

            if pr not in VALID_SCHEDULE_PROPERTIES:
                raise ValueError(
                    ERR_INVALID_SCHEDULE_PROPERTY.format(
                        pr, ", ".join(VALID_SCHEDULE_PROPERTIES)
                    )
                )

        self._set_if_specified(
            ps, PROP_METRICS, create_schedule_args, dest_name=configuration.METRICS
        )
        self._set_if_specified(
            ps, PROP_OVERWRITE, create_schedule_args, dest_name=configuration.OVERWRITE
        )
        self._set_if_specified(
            ps,
            PROP_OVERRIDE_STATUS,
            create_schedule_args,
            dest_name=configuration.OVERRIDE_STATUS,
        )
        self._set_if_specified(
            ps,
            PROP_USE_MAINTENANCE_WINDOW,
            create_schedule_args,
            dest_name=configuration.USE_MAINTENANCE_WINDOW,
        )
        self._set_if_specified(
            ps,
            PROP_ENFORCED,
            create_schedule_args,
            dest_name=configuration.ENFORCED,
            default=False,
        )
        self._set_if_specified(
            ps,
            PROP_HIBERNATE,
            create_schedule_args,
            dest_name=configuration.HIBERNATE,
            default=False,
        )
        self._set_if_specified(
            ps,
            PROP_RETAIN_RUNNING,
            create_schedule_args,
            dest_name=configuration.RETAINED_RUNNING,
            default=False,
        )
        self._set_if_specified(
            ps,
            PROP_STOP_NEW,
            create_schedule_args,
            dest_name=configuration.STOP_NEW_INSTANCES,
            default=True,
        )
        self._set_if_specified(
            ps,
            PROP_TIMEZONE,
            create_schedule_args,
            dest_name=configuration.TIMEZONE,
            default="UTC",
        )
        self._set_if_specified(
            ps,
            PROP_DESCRIPTION,
            create_schedule_args,
            dest_name=configuration.DESCRIPTION,
        )
        self._set_if_specified(
            ps,
            PROP_SSM_MAINTENANCE_WINDOW,
            create_schedule_args,
            dest_name=configuration.SSM_MAINTENANCE_WINDOW,
        )

        create_schedule_args[configuration.SCHEDULE_CONFIG_STACK] = self.stack_id

        periods = []
        try:
            self.number_of_periods = 0
            for period in ps.get(PROP_PERIODS, []):  # type:ignore[attr-defined]
                period_name, instance_type = self._create_period(period)
                if instance_type is not None:
                    period_name = "{}{}{}".format(
                        period_name, configuration.INSTANCE_TYPE_SEP, instance_type
                    )
                periods.append(period_name)

            create_schedule_args[configuration.PERIODS] = periods
            schedule = self._admin.create_schedule(create_schedule_args)  # type: ignore[arg-type]
            # todo remove the typing ignore here (requires refactoring this method)
            self.physical_resource_id = self._schedule_resource_name

            self._logger.info(INF_SCHEDULE_CREATED, safe_json(schedule, 3))
        except Exception as ex:
            self._delete_periods()
            raise ex

    def _delete_schedule(self) -> None:
        schedule = self._admin.delete_schedule(
            name=self._schedule_resource_name, exception_if_not_exists=False
        )
        if schedule is not None:
            self._delete_periods()
            self._logger.info(INF_DELETE_SCHEDULE, self._schedule_resource_name)

    def _update_schedule(self) -> None:
        self._delete_schedule()
        self._create_schedule()

    def _create_request(self) -> bool:
        try:
            self._create_schedule()
            return True
        except Exception as ex:
            self._logger.error(str(ex))
            return False
        finally:
            self._logger.flush()

    def _update_request(self) -> bool:
        try:
            self._update_schedule()
            return True
        except Exception as ex:
            self._logger.error(str(ex))
            return False
        finally:
            self._logger.flush()

            # handles Delete request from CloudFormation

    def _delete_request(self) -> bool:
        try:
            self._delete_schedule()
            return True
        except Exception as ex:
            self._logger.error(str(ex))
            return False
        finally:
            self._logger.flush()
