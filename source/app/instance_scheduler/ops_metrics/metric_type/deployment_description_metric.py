# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from dataclasses import dataclass
from typing import ClassVar

from instance_scheduler.ops_metrics import GatheringFrequency
from instance_scheduler.ops_metrics.metric_type.ops_metric import OpsMetric


@dataclass()
class ScheduleFlagCounts:
    stop_new_instances: int = 0
    enforced: int = 0
    retain_running: int = 0
    hibernate: int = 0
    override: int = 0
    use_ssm_maintenance_window: int = 0
    use_metrics: int = 0
    non_default_timezone: int = 0


@dataclass(frozen=True)
class DeploymentDescriptionMetric(OpsMetric):
    services: list[str]
    regions: list[str]
    num_accounts: int
    num_schedules: int
    num_cfn_schedules: int
    schedule_flag_counts: ScheduleFlagCounts
    default_timezone: str
    schedule_aurora_clusters: bool
    create_rds_snapshots: bool
    schedule_interval_minutes: int
    memory_size_mb: int
    using_organizations: bool
    enable_ec2_ssm_maintenance_windows: bool
    num_started_tags: int
    num_stopped_tags: int
    event_name: ClassVar[str] = "deployment_description"
    collection_frequency: ClassVar[GatheringFrequency] = GatheringFrequency.DAILY
