# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from datetime import time
from zoneinfo import ZoneInfo

from instance_scheduler.configuration.instance_schedule import InstanceSchedule
from instance_scheduler.configuration.running_period import RunningPeriod
from instance_scheduler.configuration.running_period_dict_element import (
    RunningPeriodDictElement,
)
from instance_scheduler.configuration.scheduler_config import GlobalConfig


def sample_global_config() -> GlobalConfig:
    return GlobalConfig(
        scheduled_services=["ec2"],
        schedule_clusters=False,
        tag_name="Schedule",
        regions=[],
        default_timezone=ZoneInfo("UTC"),
        schedules={
            "test-schedule": InstanceSchedule(
                name="test-schedule",
                periods=[
                    RunningPeriodDictElement(
                        period=RunningPeriod(
                            name="test-period",
                            begintime=time(10, 0, 0),
                            endtime=time(20, 0, 0),
                        )
                    )
                ],
            )
        },
        trace=False,
        enable_ssm_maintenance_windows=False,
        use_metrics=False,
        schedule_lambda_account=True,
        create_rds_snapshot=False,
        started_tags="",
        stopped_tags="",
        scheduler_role_name="Scheduler-Role",
        namespace="dev",
        organization_id="",
        aws_partition="aws",
        remote_account_ids=[],
    )
