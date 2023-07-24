# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import datetime
from typing import Any
from zoneinfo import ZoneInfo

from instance_scheduler.configuration import scheduling_context
from instance_scheduler.configuration.instance_schedule import InstanceSchedule
from instance_scheduler.configuration.running_period import RunningPeriod
from instance_scheduler.configuration.running_period_dict_element import (
    RunningPeriodDictElement,
)
from instance_scheduler.configuration.scheduling_context import (
    SchedulingContext,
    TagTemplate,
)

test_period_1 = RunningPeriod(
    name="test-period-1",
    begintime=datetime.time(9, 0, 0),
    endtime=datetime.time(17, 0, 0),
    weekdays={0, 1, 2, 3, 4},
)

test_schedule_1 = InstanceSchedule(
    name="test-schedule-1",
    timezone="UTC",
    override_status=None,
    use_metrics=True,
    periods=[RunningPeriodDictElement(period=test_period_1, instancetype=None)],
    retain_running=None,
    enforced=False,
    hibernate=False,
    use_maintenance_window=False,
    stop_new_instances=True,
)

test_schedule_2 = InstanceSchedule(
    name="test-schedule-2",
    timezone="UTC",
    override_status=None,
    use_metrics=True,
    periods=[{"period": test_period_1, "instancetype": None}],
    retain_running=None,
    enforced=False,
    hibernate=False,
    use_maintenance_window=False,
    stop_new_instances=True,
)

context = SchedulingContext(
    account_id="111122223333",
    schedule_lambda_account=True,
    service="ec2",
    region="us-east-1",
    tag_name="Schedule",
    current_dt=datetime.datetime.fromisoformat("2023-06-09T16:38:42.862261+00:00"),
    default_timezone=ZoneInfo("UTC"),
    schedules={"test-schedule-1": test_schedule_1, "test-schedule-2": test_schedule_2},
    schedule_clusters=False,
    trace=False,
    enable_ssm_maintenance_windows=False,
    use_metrics=False,
    namespace="namespace",
    aws_partition="aws",
    scheduler_role_name="scheduler-role",
    organization_id="",
    create_rds_snapshot=False,
    started_tags=[TagTemplate(Key="action", Value="started")],
    stopped_tags=[TagTemplate(Key="action", Value="stopped")],
)


expectedOut: dict[str, Any] = {
    "tag_name": "Schedule",
    "default_timezone": "UTC",
    "trace": False,
    "namespace": "namespace",
    "current_dt": "2023-06-09T16:38:42.862261+00:00",
    "scheduler_role_name": "scheduler-role",
    "organization_id": "",
    "aws_partition": "aws",
    "enable_ssm_maintenance_windows": False,
    "use_metrics": False,
    "schedule_clusters": False,
    "create_rds_snapshot": False,
    "schedule_lambda_account": True,
    "started_tags": "action=started",  # many of these are optional and not normally included in shape when none
    "stopped_tags": "action=stopped",
    "region": "us-east-1",
    "service": "ec2",
    "account_id": "111122223333",
    "schedules": {
        "test-schedule-1": {
            "name": "test-schedule-1",
            "timezone": "UTC",
            "stop_new_instances": True,
            "use_metrics": True,
            "enforced": False,
            "hibernate": False,
            "use_maintenance_window": False,
            "periods": ["test-period-1"],
        },
        "test-schedule-2": {
            "name": "test-schedule-2",
            "timezone": "UTC",
            "stop_new_instances": True,
            "use_metrics": True,
            "enforced": False,
            "hibernate": False,
            "use_maintenance_window": False,
            "periods": ["test-period-1"],
        },
    },
    "periods": {
        "test-period-1": {
            "begintime": "09:00",
            "endtime": "17:00",
            "weekdays": [0, 1, 2, 3, 4],
        },
    },
}


def test_to_dict_matches_expected_event_format() -> None:
    # print(context.to_dict())
    assert context.to_dict() == expectedOut


def test_result_of_from_dict_matches_original_object() -> None:
    dict_representation = context.to_dict()
    built_context = scheduling_context.from_dict(dict_representation)
    assert context.to_dict() == built_context.to_dict()
