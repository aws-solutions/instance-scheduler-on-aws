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

import os

import configuration
from boto_retry import get_client_with_retries


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

    def __init__(self, dt, context=None):
        """
        Initializes instance of metrics wrapper
        :param dt: date and time of the metrics data (typically the scheduling moment)
        """
        self._dt = dt
        self._metrics_managed = {}
        self._metrics_running = {}
        self._context = context
        self._stack = os.getenv(configuration.ENV_STACK)
        self._namespace = "{}:{}".format(self._stack, SchedulerMetrics.NAMESPACE)

        self._metrics_client = None

    @property
    def metrics_client(self):
        if self._metrics_client is None:
            self._metrics_client = get_client_with_retries("cloudwatch", ["put_metric_data"], context=self._context)
        return self._metrics_client

    def add_schedule_metrics(self, service, schedule, instance):
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
            self._metrics_managed[service][schedule.name] = self._metrics_managed[service].get(schedule.name, 0) + 1
            self._metrics_running[service][schedule.name] = self._metrics_running[service].get(schedule.name,
                                                                                               0) + 1 if instance.is_running else 0

    def put_schedule_metrics(self):
        """
        Writes the stores metrics data to cloudwatch metrics
        :return:
        """

        def build_metric(service_name, schedule_name, metric_name, data):
            return {
                "MetricName": metric_name,
                "Dimensions": [{"Name": SchedulerMetrics.DIMENSION_SERVICE, "Value": service_name},
                               {"Name": SchedulerMetrics.DIMENSION_SCHEDULE, "Value": schedule_name}],
                "Timestamp": self._dt,
                "Value": data[schedule_name],
                "Unit": "Count"
            }

        if len(self._metrics_managed) > 0:
            metric_data = []
            for service in list(self._metrics_managed):
                for name in list(self._metrics_managed[service]):
                    metric_data.append(
                        build_metric(service, name, SchedulerMetrics.MANAGED_INSTANCES, self._metrics_managed[service]))
                    metric_data.append(
                        build_metric(service, name, SchedulerMetrics.RUNNING_INSTANCES, self._metrics_running[service]))

            self.metrics_client.put_metric_data_with_retries(Namespace=self._namespace, MetricData=metric_data)
