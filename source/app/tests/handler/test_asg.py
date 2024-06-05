# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

from datetime import datetime, timezone
from os import environ
from typing import Final
from unittest.mock import MagicMock, patch
from uuid import UUID

from freezegun import freeze_time

from instance_scheduler.handler.asg import (
    ASG_SERVICE,
    AsgMetricsDefinition,
    send_operational_metrics,
)
from tests import DEFAULT_REGION


@patch("instance_scheduler.handler.asg.collect_metric")
def test_send_operational_metrics(mock_collect_metric: MagicMock) -> None:
    # Prepare
    metric_hour: Final = UUID(environ["METRICS_UUID"]).int % 24
    dt: Final = datetime(
        year=2024, month=4, day=23, hour=metric_hour, minute=14, tzinfo=timezone.utc
    )
    num_tagged_auto_scaling_groups = 4
    num_schedules = 1

    # Call
    with freeze_time(dt):
        send_operational_metrics(
            AsgMetricsDefinition(
                region=DEFAULT_REGION,
                num_tagged_auto_scaling_groups=num_tagged_auto_scaling_groups,
                num_schedules=num_schedules,
            )
        )

    # Verify
    assert mock_collect_metric.call_count == 1

    instance_count_metric = mock_collect_metric.call_args[1].get("metric")
    assert instance_count_metric.service == ASG_SERVICE
    assert instance_count_metric.region == DEFAULT_REGION
    assert instance_count_metric.num_instances == num_tagged_auto_scaling_groups
    assert instance_count_metric.num_schedules == num_schedules


@patch("instance_scheduler.handler.asg.collect_metric")
def test_not_send_operational_metrics_when_not_time_to_send(
    mock_collect_metric: MagicMock,
) -> None:
    # Prepare
    metric_hour: Final = UUID(environ["METRICS_UUID"]).int % 24
    current_hour = (metric_hour + 1) % 24
    dt: Final = datetime(
        year=2024, month=4, day=23, hour=current_hour, minute=14, tzinfo=timezone.utc
    )
    num_tagged_auto_scaling_groups = 4
    num_schedules = 1

    # Call
    with freeze_time(dt):
        send_operational_metrics(
            AsgMetricsDefinition(
                region=DEFAULT_REGION,
                num_tagged_auto_scaling_groups=num_tagged_auto_scaling_groups,
                num_schedules=num_schedules,
            )
        )

    # Verify
    assert mock_collect_metric.call_count == 0
