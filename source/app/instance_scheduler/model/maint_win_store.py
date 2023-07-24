# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Final

from boto3 import Session
from boto3.dynamodb.conditions import Key

from instance_scheduler.util import get_boto_config
from instance_scheduler.util.logger import Logger

if TYPE_CHECKING:
    from mypy_boto3_dynamodb.service_resource import DynamoDBServiceResource, Table
    from mypy_boto3_dynamodb.type_defs import (
        ScanInputTableScanTypeDef,
        ScanOutputTableTypeDef,
    )
    from mypy_boto3_ssm.type_defs import MaintenanceWindowIdentityTypeDef
else:
    Table = object
    ScanInputTableScanTypeDef = object
    ScanOutputTableTypeDef = object
    MaintenanceWindowIdentityTypeDef = object


class EC2SSMMaintenanceWindowStore:
    def __init__(self, *, session: Session, table_name: str, logger: Logger) -> None:
        self._logger: Final = logger
        ddb: Final[DynamoDBServiceResource] = session.resource(
            "dynamodb", config=get_boto_config()
        )
        self._table: Final[Table] = ddb.Table(table_name)

    def get_ssm_windows_db(self, *, account: str, region: str) -> list[Any]:
        """
        This function gets all the periods for a given ssm windows from the database.
        """
        maintenance_windows: ScanOutputTableTypeDef = {}  # type: ignore
        account_region_string = account + ":" + region
        try:
            scan_kwargs: ScanInputTableScanTypeDef = {
                "FilterExpression": Key("account-region").eq(account_region_string),
            }
            maintenance_windows = self._table.scan(**scan_kwargs)
        except Exception as error:
            self._logger.error(
                "Caught Exception while getting maintenance windows from Dynamodb: {}".format(
                    error
                )
            )
        window_list = maintenance_windows.get("Items", [])
        last_evaluated_key = maintenance_windows.get("LastEvaluatedKey", None)
        while last_evaluated_key is not None:
            self._logger.debug(str(maintenance_windows["LastEvaluatedKey"]))
            try:
                scan_kwargs = {
                    "FilterExpression": Key("account-region").eq(account_region_string),
                    "ExclusiveStartKey": last_evaluated_key,
                }
                maintenance_windows = self._table.scan(**scan_kwargs)
            except Exception as error:
                self._logger.error(
                    "Caught Exception while getting maintenance windows from Dynamodb: {}".format(
                        error
                    )
                )
            last_evaluated_key = maintenance_windows.get("LastEvaluatedKey", None)
            window_list.extend(maintenance_windows.get("Items", []))
        return window_list

    def put_window_dynamodb(
        self, *, window: MaintenanceWindowIdentityTypeDef, account: str, region: str
    ) -> None:
        """
        This function adds the ssm window entry to the database.

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

            ttl = execution_time + timedelta(hours=int(duration))
            epoch_time_to_live = int(
                datetime(ttl.year, ttl.month, ttl.day, ttl.hour, ttl.minute).timestamp()
            )
            self._table.put_item(
                Item={
                    "Name": window["Name"],
                    "NextExecutionTime": window["NextExecutionTime"],
                    "Duration": window["Duration"],
                    "WindowId": window["WindowId"],
                    "TimeToLive": epoch_time_to_live,
                    "account-region": account + ":" + region,
                    "ScheduleTimezone": window["ScheduleTimezone"],
                }
            )
        except Exception as error:
            self._logger.info(
                "Unable to put maintenance window in Dynamodb: {}".format(error)
            )

    def delete_window(self, window: Any) -> None:
        self._table.delete_item(
            Key={
                "Name": window["Name"],
                "account-region": window["account-region"],
            }
        )
