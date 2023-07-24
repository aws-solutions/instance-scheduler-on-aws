# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

from instance_scheduler.boto_retry import get_client_with_standard_retry
from instance_scheduler.configuration.instance_schedule import (
    Instance,
    InstanceSchedule,
)
from instance_scheduler.util.app_env import get_app_env

if TYPE_CHECKING:
    from mypy_boto3_cloudwatch.client import CloudWatchClient
    from mypy_boto3_cloudwatch.type_defs import MetricDatumTypeDef
else:
    CloudWatchClient = object
    MetricDatumTypeDef = object


class SchedulerMetrics:
    """
    Implements wrapper to write metrics data
    """

    NAMESPACE = "InstanceScheduler"
    RUNNING_INSTANCES = "RunningInstances"
    MANAGED_INSTANCES = "ManagedInstances"
    DIMENSION_SCHEDULE = "Schedule"
    DIMENSION_SERVICE = "Service"
    ERRORS = "Errors"
    WARNINGS = "Warnings"

    def __init__(self, dt: datetime) -> None:
        """
        Initializes instance of metrics wrapper
        :param dt: date and time of the metrics data (typically the scheduling moment)
        """
        self._dt = dt
        self._metrics_managed: dict[str, dict[str, int]] = {}
        self._metrics_running: dict[str, dict[str, int]] = {}
        self._stack = get_app_env().stack_name
        self._namespace = "{}:{}".format(self._stack, SchedulerMetrics.NAMESPACE)

        self._metrics_client: Optional[CloudWatchClient] = None

    @property
    def metrics_client(self) -> CloudWatchClient:
        if self._metrics_client is None:
            self._metrics_client = get_client_with_standard_retry("cloudwatch")
        return self._metrics_client

    def add_schedule_metrics(
        self, service: str, schedule: InstanceSchedule, instance: Instance
    ) -> None:
        """
        Adds metrics data
        :param service: name of the service
        :param schedule: name of the schedule
        :param instance: scheduled instance
        :return:
        """
        if schedule.use_metrics:
            if service not in self._metrics_managed:
                self._metrics_managed[service] = {}
                self._metrics_running[service] = {}
            self._metrics_managed[service][schedule.name] = (
                self._metrics_managed[service].get(schedule.name, 0) + 1
            )
            self._metrics_running[service][schedule.name] = (
                self._metrics_running[service].get(schedule.name, 0) + 1
                if instance["is_running"]
                else 0
            )

    def put_schedule_metrics(self) -> None:
        """
        Writes the stores metrics data to cloudwatch metrics
        :return:
        """

        def build_metric(
            service_name: str,
            schedule_name: str,
            metric_name: str,
            data: dict[str, Any],
        ) -> MetricDatumTypeDef:
            return {
                "MetricName": metric_name,
                "Dimensions": [
                    {"Name": SchedulerMetrics.DIMENSION_SERVICE, "Value": service_name},
                    {
                        "Name": SchedulerMetrics.DIMENSION_SCHEDULE,
                        "Value": schedule_name,
                    },
                ],
                "Timestamp": self._dt,
                "Value": data[schedule_name],
                "Unit": "Count",
            }

        if len(self._metrics_managed) > 0:
            metric_data = []
            for service in list(self._metrics_managed):
                for name in list(self._metrics_managed[service]):
                    metric_data.append(
                        build_metric(
                            service,
                            name,
                            SchedulerMetrics.MANAGED_INSTANCES,
                            self._metrics_managed[service],
                        )
                    )
                    metric_data.append(
                        build_metric(
                            service,
                            name,
                            SchedulerMetrics.RUNNING_INSTANCES,
                            self._metrics_running[service],
                        )
                    )

            self.metrics_client.put_metric_data(
                Namespace=self._namespace, MetricData=metric_data
            )
