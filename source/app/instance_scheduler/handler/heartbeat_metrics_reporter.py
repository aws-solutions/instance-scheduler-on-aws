# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import traceback
from typing import Any, Final, Mapping

from aws_lambda_powertools.utilities.typing import LambdaContext
from instance_scheduler.handler.environments.heartbeat_metrics_environment import (
    HeartbeatMetricsEnvironment,
)
from instance_scheduler.model.store.dynamo_period_definition_store import (
    DynamoPeriodDefinitionStore,
)
from instance_scheduler.model.store.dynamo_resource_registry import (
    DynamoResourceRegistry,
)
from instance_scheduler.model.store.dynamo_schedule_definition_store import (
    DynamoScheduleDefinitionStore,
)
from instance_scheduler.observability.powertools_logging import (
    powertools_logger,
    should_log_events,
)
from instance_scheduler.ops_metrics.metric_type.deployment_description_metric import (
    DeploymentDescriptionMetric,
    ScheduleFlagCounts,
)
from instance_scheduler.ops_metrics.metric_type.instance_count_metric import (
    InstanceCountMetric,
)
from instance_scheduler.ops_metrics.metrics import collect_metric

logger: Final = powertools_logger()


@logger.inject_lambda_context(log_event=should_log_events(logger))
def report_heartbeat_metric(event: Mapping[str, Any], context: LambdaContext) -> Any:
    env: Final = HeartbeatMetricsEnvironment.from_env()

    try:
        schedule_store = DynamoScheduleDefinitionStore(env.config_table_name)
        period_store = DynamoPeriodDefinitionStore(env.config_table_name)

        # count usage of scheduling features
        flag_counts = ScheduleFlagCounts()
        schedules = schedule_store.find_all()
        periods = period_store.find_all()

        for schedule in schedules.values():
            flag_counts.stop_new_instances += schedule.stop_new_instances in [
                True,
                None,
            ]
            flag_counts.enforced += schedule.enforced is True
            flag_counts.retain_running += schedule.retain_running is True
            flag_counts.hibernate += schedule.hibernate is True
            flag_counts.override += schedule.override_status is not None
            flag_counts.use_ssm_maintenance_window += bool(
                schedule.ssm_maintenance_window
            )
            flag_counts.non_default_timezone += schedule.timezone != str(
                env.default_timezone
            )

        one_sided_schedules = 0
        for schedule in schedules.values():
            for schedule_period in schedule.periods:
                period = periods.get(schedule_period.name)
                if period and (
                    (period.begintime and not period.endtime)
                    or (not period.begintime and period.endtime)
                ):
                    one_sided_schedules += 1
                    break

        # count resource metrics
        registry = DynamoResourceRegistry(env.registry_table)

        total_resources = 0
        total_targets = 0
        accounts = set()
        services = set()
        regions = set()

        for target in registry.list_all_by_scheduling_target():
            total_resources += len(target.resources)
            total_targets += 1
            accounts.add(target.account)
            services.add(target.service)
            regions.add(target.region)

            collect_metric(
                InstanceCountMetric(
                    service=target.service,
                    region=target.region,
                    account=target.account,
                    num_instances=len(target.resources),
                    num_schedules=len(
                        {resource.schedule for resource in target.resources}
                    ),
                ),
                logger,
            )

        cfn_schedules = sum(
            1 for schedule in schedules.values() if schedule.configured_in_stack
        )

        heartbeat_metric = DeploymentDescriptionMetric(
            services=list(services),
            regions=list(regions),
            num_resources=total_resources,
            num_targets=total_targets,
            num_accounts=len(accounts),
            num_schedules=len(schedules),
            num_cfn_schedules=cfn_schedules,
            num_one_sided_schedules=one_sided_schedules,
            schedule_flag_counts=flag_counts,
            default_timezone=str(env.default_timezone),
            create_rds_snapshots=env.enable_rds_snapshots,
            schedule_interval_minutes=env.scheduler_frequency_minutes,
            memory_size_mb=context.memory_limit_in_mb,
            using_organizations=env.enable_aws_organizations,
            enable_ec2_ssm_maintenance_windows=env.enable_ec2_ssm_maintenance_windows,
            ops_dashboard_enabled=env.ops_dashboard_enabled,
            num_started_tags=0,
            num_stopped_tags=0,
            approximate_lambda_payload_size_bytes=0,
        )

        collect_metric(heartbeat_metric, logger)

        return {"status": "success"}
    except Exception as e:
        logger.warning(
            f"Error reporting heartbeat metrics: ({e})\n{traceback.format_exc()}"
        )
