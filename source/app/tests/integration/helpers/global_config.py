# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from typing import Optional
from zoneinfo import ZoneInfo

from instance_scheduler.configuration.instance_schedule import InstanceSchedule
from instance_scheduler.configuration.scheduler_config import GlobalConfig


def build_global_config(
    schedules: dict[str, InstanceSchedule],
    remote_account_ids: Optional[list[str]] = None,
    scheduled_services: Optional[list[str]] = None,
    regions: Optional[list[str]] = None,
    tag_name: str = "Schedule",
    default_timezone: str = "UTC",
    schedule_clusters: bool = False,
    trace: bool = False,
    enable_ssm_maintenance_windows: bool = False,
    use_metrics: bool = False,
    namespace: str = "namespace",
    aws_partition: str = "aws",
    scheduler_role_name: str = "scheduler_role",
    organization_id: str = "",
    schedule_lambda_account: bool = True,
    create_rds_snapshot: bool = False,
    started_tags: str = "",
    stopped_tags: str = "",
) -> GlobalConfig:
    if remote_account_ids is None:
        remote_account_ids = []
    if scheduled_services is None:
        scheduled_services = ["ec2"]
    if regions is None:
        regions = ["us-east-1"]

    return GlobalConfig(
        schedules=schedules,
        remote_account_ids=remote_account_ids,
        scheduled_services=scheduled_services,
        regions=regions,
        tag_name=tag_name,
        default_timezone=ZoneInfo(default_timezone),
        schedule_clusters=schedule_clusters,
        trace=trace,
        enable_ssm_maintenance_windows=enable_ssm_maintenance_windows,
        use_metrics=use_metrics,
        namespace=namespace,
        aws_partition=aws_partition,
        scheduler_role_name=scheduler_role_name,
        organization_id=organization_id,
        schedule_lambda_account=schedule_lambda_account,
        create_rds_snapshot=create_rds_snapshot,
        started_tags=started_tags,
        stopped_tags=stopped_tags,
    )
