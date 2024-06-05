# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from os import environ
from typing import Any, Callable, ClassVar, TypeVar
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

from freezegun import freeze_time

from instance_scheduler.ops_metrics import GatheringFrequency
from instance_scheduler.ops_metrics.metric_type.ops_metric import OpsMetric
from instance_scheduler.ops_metrics.metrics import collect_metric, should_collect_metric
from tests.logger import MockLogger
from tests.test_utils.mock_metrics_environment import MockMetricsEnviron


@dataclass(frozen=True)
class UnlimitedTestMetric(OpsMetric):
    collection_frequency: ClassVar[GatheringFrequency] = GatheringFrequency.UNLIMITED
    event_name: ClassVar[str] = "unlimited-metrics"
    context_version: ClassVar[int] = 1


@dataclass(frozen=True)
class DailyTestMetric(OpsMetric):
    collection_frequency: ClassVar[GatheringFrequency] = GatheringFrequency.DAILY
    event_name: ClassVar[str] = "daily-metrics"
    context_version: ClassVar[int] = 1


FuncT = TypeVar("FuncT", bound=Callable[..., Any])


def test_metrics_disabled_when_environment_is_missing() -> None:
    environ.clear()
    assert not should_collect_metric(UnlimitedTestMetric())


def test_attempting_to_collect_metrics_when_environ_is_missing_does_not_cause_error() -> (
    None
):
    environ.clear()
    collect_metric(UnlimitedTestMetric(), MockLogger())
    collect_metric(DailyTestMetric(), MockLogger())


def test_metrics_not_collected_when_disabled() -> None:
    with MockMetricsEnviron(send_anonymous_metrics=False):
        assert not should_collect_metric(UnlimitedTestMetric())


def test_unlimited_metric_should_be_sent() -> None:
    with MockMetricsEnviron(send_anonymous_metrics=True):
        assert should_collect_metric(UnlimitedTestMetric)


def test_daily_metric_should_only_be_sent_once_daily() -> None:
    with MockMetricsEnviron(send_anonymous_metrics=True):
        minutes_in_day = 1440
        start_of_day = datetime(2023, 6, 23, 0, 0, 0)

        for interval in [5, 30, 60]:  # test intervals of 5, 30, and 60 minutes
            num_metrics_gathered = 0
            for offset in range(0, minutes_in_day, interval):
                sim_time = start_of_day + timedelta(minutes=offset)
                with patch.dict(
                    environ, {"SCHEDULER_FREQUENCY": str(interval)}
                ), freeze_time(sim_time):
                    if should_collect_metric(DailyTestMetric):
                        num_metrics_gathered += 1

            assert (
                num_metrics_gathered == 1
            ), "failed to gather specified number of metrics with interval:{} see output log for uuid used".format(
                interval
            )


def test_collect_metric_does_nothing_when_should_collect_returns_false(
    mock_metrics_endpoint: MagicMock,
) -> None:
    with patch(
        "instance_scheduler.ops_metrics.metrics.should_collect_metric"
    ) as should_collect_metric_func:
        should_collect_metric_func.return_value = False
        collect_metric(metric=UnlimitedTestMetric(), logger=MockLogger())
        assert mock_metrics_endpoint.call_count == 0


@freeze_time(datetime(2023, 6, 23, 10, 0, 5, tzinfo=ZoneInfo("UTC")))
def test_collect_metric_sends_metric_when_should_collect_returns_true(
    mock_metrics_endpoint: MagicMock,
) -> None:
    with MockMetricsEnviron() as metrics_environ, patch(
        "instance_scheduler.ops_metrics.metrics.should_collect_metric"
    ) as should_collect_metric_func:
        should_collect_metric_func.return_value = True
        collect_metric(metric=UnlimitedTestMetric(), logger=MockLogger())

        expected_data = json.dumps(
            {
                "timestamp": "2023-06-23 10:00:05",
                "uuid": str(metrics_environ.metrics_uuid),
                "solution": metrics_environ.solution_id,
                "version": metrics_environ.solution_version,
                "event_name": "unlimited-metrics",
                "context_version": 1,
                "context": {},
            },
            indent=0,
        )

        expected_headers = {
            "content-type": "application/json",
            "content-length": str(len(expected_data)),
        }

        mock_metrics_endpoint.assert_called_once_with(
            "POST",
            metrics_environ.anonymous_metrics_url,
            body=expected_data,
            headers=expected_headers,
        )
