# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from datetime import datetime, timezone
from enum import StrEnum
from functools import cached_property
from itertools import batched
from typing import TYPE_CHECKING, Iterable, TypedDict

from instance_scheduler.handler.environments.scheduling_request_environment import (
    SchedulingRequestEnvironment,
)
from instance_scheduler.observability.instance_counts import ServiceInstanceCounts
from instance_scheduler.observability.powertools_logging import powertools_logger
from instance_scheduler.ops_metrics.metric_type.insights_metric import (
    Dimension,
    MetricDataItem,
)
from instance_scheduler.util.session_manager import lambda_execution_role

if TYPE_CHECKING:
    from mypy_boto3_cloudwatch import CloudWatchClient
else:
    CloudWatchClient = object


class InstanceData(TypedDict):
    stopped: int
    total: int


"""str is instance type"""
InstanceDataByInstanceType = dict[str, InstanceData]

"""str is service"""
ServicesInstanceData = dict[str, InstanceDataByInstanceType]
"""
sample data shape
{
  "ec2": {
    "t2.micro": {
      stopped: 5
      total: 10
    }
  },
  "rds": {
    "m2.medium": {
      stopped: 1
      total: 1
    }
  }
}
"""


class MetricName(StrEnum):
    ManagedInstances = "ManagedInstances"
    StoppedInstances = "StoppedInstances"
    RunningInstances = "RunningInstances"


class DimensionName(StrEnum):
    Service = "Service"
    InstanceType = "InstanceType"
    Schedule = "Schedule"
    SchedulingInterval = "SchedulingInterval"


logger = powertools_logger()


class CloudWatchOperationalInsights:
    def __init__(
        self,
        env: SchedulingRequestEnvironment,
    ) -> None:
        self._namespace = f"{env.hub_stack_name}:InstanceScheduler"

    @cached_property
    def cloudwatch_client(self) -> CloudWatchClient:
        client: CloudWatchClient = lambda_execution_role().client("cloudwatch")
        return client

    def send_metrics_to_cloudwatch(
        self,
        instance_counts: ServiceInstanceCounts,
        scheduling_interval_minutes: int,
    ) -> None:
        metrics_to_send = self.build_per_instance_type_metrics(
            instance_counts, scheduling_interval_minutes
        )

        self.send_to_cloudwatch(metrics_to_send)

    # disabled in 3.1.0 to save cost
    @staticmethod
    def build_per_schedule_metrics(
        aggregated_instances: ServiceInstanceCounts,
        scheduling_interval_minutes: int,
    ) -> list[MetricDataItem]:
        metric_data = []

        for service, instance_counts in aggregated_instances.items():
            for schedule_name, counts in instance_counts.by_schedule().items():
                managed_per_sched_metric = (
                    CloudWatchOperationalInsights.build_per_schedule_metric(
                        service=service,
                        schedule_name=schedule_name,
                        scheduling_interval_minutes=scheduling_interval_minutes,
                        metric_name=MetricName.ManagedInstances,
                        metric_value=counts.total(),
                    )
                )
                running_per_sched_metric = (
                    CloudWatchOperationalInsights.build_per_schedule_metric(
                        service=service,
                        schedule_name=schedule_name,
                        scheduling_interval_minutes=scheduling_interval_minutes,
                        metric_name=MetricName.RunningInstances,
                        metric_value=counts["running"],
                    )
                )
                metric_data.extend([managed_per_sched_metric, running_per_sched_metric])

        return metric_data

    def send_to_cloudwatch(self, metric_data: Iterable[MetricDataItem]) -> None:
        # actual batch limit is 1000 metrics, but there is also a 1MB payload limit which we are not directly checking
        # so this should give plenty of overhead
        batch_size = 500
        try:
            cw_data = [metric.to_cloudwatch_data() for metric in metric_data]

            for batch in batched(cw_data, batch_size):
                self.cloudwatch_client.put_metric_data(
                    Namespace=self._namespace,
                    MetricData=list(batch),
                )

        except Exception as e:
            logger.warning(f"Error sending metric data to cloudwatch: {e}")

    @staticmethod
    def build_per_schedule_metric(
        service: str,
        schedule_name: str,
        scheduling_interval_minutes: int,
        metric_name: MetricName,
        metric_value: int,
    ) -> MetricDataItem:
        return MetricDataItem(
            metric_name=metric_name,
            dimensions=[
                Dimension(
                    name=DimensionName.Service,
                    value=service,
                ),
                Dimension(
                    name=DimensionName.Schedule,
                    value=schedule_name,
                ),
                Dimension(
                    name=DimensionName.SchedulingInterval,
                    value=str(scheduling_interval_minutes),
                ),
            ],
            timestamp=datetime.now(timezone.utc),
            value=metric_value,
            unit="Count",
        )

    @staticmethod
    def build_per_instance_type_metric(
        service: str,
        instance_type: str,
        scheduling_interval_minutes: int,
        metric_name: MetricName,
        metric_value: int,
    ) -> MetricDataItem:
        return MetricDataItem(
            metric_name=metric_name,
            dimensions=[
                Dimension(
                    name=DimensionName.Service,
                    value=service,
                ),
                Dimension(
                    name=DimensionName.InstanceType,
                    value=instance_type,
                ),
                Dimension(
                    name=DimensionName.SchedulingInterval,
                    value=str(scheduling_interval_minutes),
                ),
            ],
            timestamp=datetime.now(timezone.utc),
            value=metric_value,
            unit="Count",
        )

    @staticmethod
    def build_per_instance_type_metrics(
        aggregated_instances: ServiceInstanceCounts,
        scheduling_interval_minutes: int,
    ) -> list[MetricDataItem]:
        """
        convert from raw scan data to metric items that can be sent to cloudwatch/aws
        aggregated on a per-instance basis
        """
        metric_data = []

        for service, instance_counts in aggregated_instances.items():
            for instance_type, counts in instance_counts.by_type().items():
                total_controlled_per_instance_metric = (
                    CloudWatchOperationalInsights.build_per_instance_type_metric(
                        service=service,
                        instance_type=instance_type,
                        scheduling_interval_minutes=scheduling_interval_minutes,
                        metric_name=MetricName.ManagedInstances,
                        metric_value=counts.total(),
                    )
                )
                stopped_per_instance_metric = (
                    CloudWatchOperationalInsights.build_per_instance_type_metric(
                        service=service,
                        instance_type=instance_type,
                        scheduling_interval_minutes=scheduling_interval_minutes,
                        metric_name=MetricName.StoppedInstances,
                        metric_value=counts["stopped"],
                    )
                )
                running_per_instance_metric = (
                    CloudWatchOperationalInsights.build_per_instance_type_metric(
                        service=service,
                        instance_type=instance_type,
                        scheduling_interval_minutes=scheduling_interval_minutes,
                        metric_name=MetricName.RunningInstances,
                        metric_value=counts["running"],
                    )
                )
                metric_data.extend(
                    [
                        total_controlled_per_instance_metric,
                        stopped_per_instance_metric,
                        running_per_instance_metric,
                    ]
                )

        return metric_data
