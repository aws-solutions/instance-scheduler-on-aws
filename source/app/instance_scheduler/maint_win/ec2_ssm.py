# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Final, Literal
from zoneinfo import ZoneInfo

import dateutil.parser
from boto3 import Session

from instance_scheduler.boto_retry import get_client_with_standard_retry
from instance_scheduler.configuration.instance_schedule import InstanceSchedule
from instance_scheduler.configuration.running_period import RunningPeriod
from instance_scheduler.configuration.running_period_dict_element import (
    RunningPeriodDictElement,
)
from instance_scheduler.configuration.scheduler_config_builder import (
    SchedulerConfigBuilder,
)
from instance_scheduler.model import EC2SSMMaintenanceWindowStore
from instance_scheduler.util.logger import Logger

if TYPE_CHECKING:
    from mypy_boto3_ssm.client import SSMClient
    from mypy_boto3_ssm.type_defs import (
        DescribeMaintenanceWindowsResultTypeDef,
        MaintenanceWindowIdentityTypeDef,
    )
else:
    SSMClient = object
    DescribeMaintenanceWindowsResultTypeDef = object
    MaintenanceWindowIdentityTypeDef = object


class EC2SSMMaintenanceWindows:
    def __init__(
        self,
        *,
        hub_session: Session,
        spoke_session: Session,
        spoke_account_id: str,
        table_name: str,
        scheduler_interval: int,
        logger: Logger,
    ) -> None:
        self._spoke_session: Final = spoke_session
        self._spoke_account_id = spoke_account_id
        self._scheduler_interval = scheduler_interval
        self._logger: Final = logger

        self._region: Final = self._spoke_session.region_name
        self._store: Final = EC2SSMMaintenanceWindowStore(
            session=hub_session, table_name=table_name, logger=self._logger
        )

    def get_ssm_windows_service(
        self, session: Session, region: str
    ) -> list[MaintenanceWindowIdentityTypeDef]:
        """
        This function gets all the ssm windows which are enabled from SSM service.

        Returns:
            list of ssm windows
        """
        ssm_client: SSMClient = get_client_with_standard_retry(
            "ssm", session=session, region=region
        )
        resp_maintenance_windows: DescribeMaintenanceWindowsResultTypeDef = {}  # type: ignore
        try:
            resp_maintenance_windows = ssm_client.describe_maintenance_windows(
                Filters=[
                    {
                        "Key": "Enabled",
                        "Values": [
                            "true",
                        ],
                    },
                ]
            )
        except Exception as error:
            self._logger.error(
                "Caught Exception while getting the maintenance window: {}".format(
                    error
                )
            )
        ssm_window_list = resp_maintenance_windows.get("WindowIdentities", [])
        next_token = resp_maintenance_windows.get("NextToken", None)
        while next_token is not None:
            try:
                resp_maintenance_windows = ssm_client.describe_maintenance_windows(
                    Filters=[
                        {
                            "Key": "Enabled",
                            "Values": [
                                "true",
                            ],
                        },
                    ],
                    NextToken=next_token,
                )
            except Exception as error:
                self._logger.error(
                    "Caught Exception while getting the maintenance window: {}".format(
                        error
                    )
                )
            next_token = resp_maintenance_windows.get("NextToken", None)
            ssm_window_list.extend(resp_maintenance_windows.get("WindowIdentities", []))
        return ssm_window_list

    def process_ssm_window(
        self,
        window: MaintenanceWindowIdentityTypeDef,
        ssm_windows_db: list[Any],
        account: str,
        region: str,
    ) -> MaintenanceWindowIdentityTypeDef:
        """
        This function checks if the window is enabled before adding it to the db and update the db for disabled windows.

        Parameters:
            SSM window object
            List of maintenance windows from db
        """
        new_ssm_window: MaintenanceWindowIdentityTypeDef = {}
        current_window = {}
        for window_db in ssm_windows_db:
            if window_db["Name"] == window["Name"]:
                current_window = window_db  # get the window from the db with the same name as the window from service
                break
        if current_window.get("Name") is None:
            self._store.put_window_dynamodb(
                window=window, account=account, region=region
            )
            new_ssm_window = window
        else:
            if not self.check_window_running(current_window):
                self._store.put_window_dynamodb(
                    window=window, account=account, region=region
                )

        return new_ssm_window

    def check_window_running(self, window: Any) -> bool:
        """
        This function checks if given maintenance window is currently running.

        Parameters:
            SSM window object
        """
        try:
            duration = window["Duration"]
            if "ScheduleTimezone" in window:
                execution_time = datetime.strptime(
                    window["NextExecutionTime"], "%Y-%m-%dT%H:%M%z"
                )
            else:
                execution_time = datetime.strptime(
                    window["NextExecutionTime"], "%Y-%m-%dT%H:%MZ"
                )
                window["ScheduleTimezone"] = "UTC"

            tz = ZoneInfo(window["ScheduleTimezone"])
            window_begin_time = execution_time.replace(tzinfo=tz)
            window_end_time = execution_time.replace(tzinfo=tz) + timedelta(
                hours=int(duration)
            )
            current_time = datetime.now(tz).replace(tzinfo=tz)
            return window_begin_time < current_time < window_end_time
        except Exception as ex:
            self._logger.error("error in check_window_running {}".format(ex))
            return False

    def remove_unused_windows(
        self,
        *,
        window_db: Any,
        ssm_windows_service: list[MaintenanceWindowIdentityTypeDef],
    ) -> None:
        """
        This function removes the old windows not present in the ssm service response.
        """
        window_found = False
        for window_service in ssm_windows_service:
            if window_service["Name"] == window_db["Name"]:
                window_found = True
                break
        if not window_found:
            try:  # if window from db is not found in the SSM response delete the entry from db
                self._store.delete_window(window_db)
            except Exception as error:
                self._logger.error(
                    "Caught Exception while deleting maintenance windows from Dynamodb: {}".format(
                        error
                    )
                )

    def get_ssm_windows(self, session: Session, account: str, region: str) -> list[Any]:
        """
        This function gets the list of the SSM maintenance windows
        """
        new_ssm_windows_list = []
        ssm_windows_service = self.get_ssm_windows_service(session, region)
        ssm_windows_db = self._store.get_ssm_windows_db(account=account, region=region)
        for window_service in ssm_windows_service:
            new_maintenance_window = self.process_ssm_window(
                window_service, ssm_windows_db, account, region
            )
            if new_maintenance_window:
                new_ssm_windows_list.append(new_maintenance_window)
        for window_db in ssm_windows_db:
            self.remove_unused_windows(
                window_db=window_db, ssm_windows_service=ssm_windows_service
            )
        for window in new_ssm_windows_list:
            ssm_windows_db.append(window)
        return ssm_windows_db

    def ssm_maintenance_windows(
        self, session: Session, account: str, region: str
    ) -> dict[str, InstanceSchedule | Literal["NOT-FOUND"]]:
        windows: dict[str, InstanceSchedule | Literal["NOT-FOUND"]] = {}
        try:
            window_list = self.get_ssm_windows(session, account, region)
            for window in window_list:
                start = dateutil.parser.parse(window["NextExecutionTime"])
                scheduler_timezone = window.get("ScheduleTimezone", "UTC")
                maintenance_schedule = self._schedule_from_maint_window(
                    name=window["Name"],
                    start=start,
                    interval=self._scheduler_interval,
                    hours=int(window["Duration"]),
                    timezone=scheduler_timezone,
                )
                windows[str(window["Name"])] = maintenance_schedule
        except Exception as ex:
            self._logger.error("Error loading ssm maintenace windows, ({})".format(ex))

        return windows

    def _schedule_from_maint_window(
        self, name: str, start: datetime, hours: int, interval: int, timezone: str
    ) -> InstanceSchedule:
        start_dt = start.replace(second=0, microsecond=0)
        start_before_begin = interval + 10
        begin_dt = start_dt - timedelta(minutes=start_before_begin)
        end_dt = start_dt + timedelta(hours=hours)
        if begin_dt.day == end_dt.day:
            periods: list[RunningPeriodDictElement] = [
                {
                    "period": RunningPeriod(
                        name="{}-period".format(name),
                        begintime=begin_dt.time(),
                        endtime=end_dt.time(),
                        monthdays={begin_dt.day},
                        months={begin_dt.month},
                    ),
                    "instancetype": None,
                }
            ]
        elif end_dt - begin_dt <= timedelta(hours=24):
            periods = [
                {
                    "period": RunningPeriod(
                        name="{}-period-1".format(name),
                        begintime=begin_dt.time(),
                        endtime=SchedulerConfigBuilder.get_time_from_string("23:59"),
                        monthdays={begin_dt.day},
                        months={begin_dt.month},
                    ),
                    "instancetype": None,
                },
                {
                    "period": RunningPeriod(
                        name="{}-period-2".format(name),
                        begintime=SchedulerConfigBuilder.get_time_from_string("00:00"),
                        endtime=end_dt.time(),
                        monthdays={end_dt.day},
                        months={end_dt.month},
                    ),
                    "instancetype": None,
                },
            ]
        else:
            periods = [
                {
                    "period": RunningPeriod(
                        name="{}-period-1".format(name),
                        begintime=begin_dt.time(),
                        endtime=SchedulerConfigBuilder.get_time_from_string("23:59"),
                        monthdays={begin_dt.day},
                        months={begin_dt.month},
                    ),
                    "instancetype": None,
                },
                {
                    "period": RunningPeriod(
                        name="{}-period-2".format(name),
                        monthdays={(end_dt - timedelta(days=1)).day},
                        months={(end_dt - timedelta(days=1)).month},
                    ),
                    "instancetype": None,
                },
                {
                    "period": RunningPeriod(
                        name="{}-period-3".format(name),
                        begintime=SchedulerConfigBuilder.get_time_from_string("00:00"),
                        endtime=end_dt.time(),
                        monthdays={end_dt.day},
                        months={end_dt.month},
                    ),
                    "instancetype": None,
                },
            ]

        schedule = InstanceSchedule(
            name=name,
            timezone=timezone,
            description="{} maintenance window".format(name),
            enforced=True,
            periods=periods,
        )

        self._logger.info(
            "Created schedule {} from SSM maintence window, start is {}, end is {}",
            name,
            begin_dt.isoformat(),
            end_dt.isoformat(),
        )

        return schedule
