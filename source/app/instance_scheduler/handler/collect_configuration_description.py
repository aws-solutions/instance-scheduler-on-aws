# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import dataclasses
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Literal, Mapping, TypedDict

from typing_extensions import TypeGuard

from instance_scheduler import configuration
from instance_scheduler.configuration.instance_schedule import InstanceSchedule
from instance_scheduler.configuration.scheduler_config import GlobalConfig
from instance_scheduler.handler.base import Handler
from instance_scheduler.ops_metrics.metric_type.configuration_description_metric import (
    ConfigurationDescriptionMetric,
    ScheduleFlagCounts,
)
from instance_scheduler.ops_metrics.metrics import collect_metric
from instance_scheduler.util.app_env import AppEnv, get_app_env
from instance_scheduler.util.logger import Logger

if TYPE_CHECKING:
    from aws_lambda_powertools.utilities.typing import LambdaContext
else:
    LambdaContext = object


class CollectConfigurationMetricsRequest(TypedDict):
    scheduled_action: Literal["collect_configuration_metrics"]


class CollectConfigurationDescription(Handler[CollectConfigurationMetricsRequest]):
    def __init__(
        self, event: CollectConfigurationMetricsRequest, context: LambdaContext
    ) -> None:
        self._context = context

        # Setup logging
        classname = self.__class__.__name__
        app_env = get_app_env()
        dt = datetime.now(timezone.utc)
        logstream = "{}-{:0>4d}{:0>2d}{:0>2d}".format(
            classname, dt.year, dt.month, dt.day
        )
        self._logger = Logger(
            log_group=app_env.log_group,
            log_stream=logstream,
            topic_arn=app_env.topic_arn,
        )

    @staticmethod
    def is_handling_request(
        event: Mapping[str, Any]
    ) -> TypeGuard[CollectConfigurationMetricsRequest]:
        return str(event.get("scheduled_action", "")) == "collect_configuration_metrics"

    def handle_request(self) -> Any:
        with self._logger:
            global_config = configuration.get_global_configuration(self._logger)
            app_env = get_app_env()
            metric = self.build_ops_metric(
                global_config=global_config,
                app_env=app_env,
                lambda_context=self._context,
            )

            sent_metric = collect_metric(
                metric,
                logger=self._logger,
            )

            if sent_metric:
                return {"sent_metric": dataclasses.asdict(sent_metric)}
            else:
                return {"sent_metric": {}}

    @staticmethod
    def build_ops_metric(
        global_config: GlobalConfig,
        app_env: AppEnv,
        lambda_context: LambdaContext,
    ) -> ConfigurationDescriptionMetric:
        flag_counts = ScheduleFlagCounts()
        for schedule in global_config.schedules.values():
            flag_counts.stop_new_instances += schedule.stop_new_instances is True
            flag_counts.enforced += schedule.enforced is True
            flag_counts.retain_running += schedule.retain_running is True
            flag_counts.hibernate += schedule.hibernate is True
            flag_counts.override += schedule.override_status is not None
            flag_counts.use_ssm_maintenance_window += (
                schedule.use_maintenance_window is True
            )
            flag_counts.use_metrics += schedule.use_metrics is True
            flag_counts.non_default_timezone += schedule.timezone != str(
                global_config.default_timezone
            )

        metric = ConfigurationDescriptionMetric(
            num_schedules=len(global_config.schedules),
            num_cfn_schedules=CollectConfigurationDescription._count_cfn_schedules(
                global_config.schedules
            ),
            schedule_flag_counts=flag_counts,
            default_timezone=str(global_config.default_timezone),
            schedule_aurora_clusters=global_config.schedule_clusters,
            create_rds_snapshots=global_config.create_rds_snapshot,
            schedule_interval_minutes=app_env.scheduler_frequency_minutes,
            memory_size_mb=lambda_context.memory_limit_in_mb,
            using_organizations=app_env.enable_aws_organizations,
            enable_ec2_ssm_maintenance_windows=app_env.enable_ec2_ssm_maintenance_windows,
            num_started_tags=len(app_env.start_tags),
            num_stopped_tags=len(app_env.stop_tags),
        )

        return metric

    @classmethod
    def _count_cfn_schedules(cls, schedules: dict[str, InstanceSchedule]) -> int:
        count = 0
        for schedule in schedules.values():
            count += bool(schedule.configured_in_stack)
        return count
