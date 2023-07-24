# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import wraps
from os import environ
from typing import Any, Callable, ClassVar, TypeVar, cast
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

from freezegun import freeze_time

from instance_scheduler.ops_metrics import GatheringFrequency, metrics
from instance_scheduler.ops_metrics.metric_type.ops_metric import OpsMetric
from instance_scheduler.ops_metrics.metrics import collect_metric, should_collect_metric
from instance_scheduler.util.app_env import AppEnv
from tests.integration.ops_metrics.conftest import solution_metrics_uuid
from tests.logger import MockLogger


@dataclass(frozen=True)
class UnlimitedTestMetric(OpsMetric):
    collection_frequency: ClassVar[GatheringFrequency] = GatheringFrequency.UNLIMITED
    event_name: ClassVar[str] = "unlimited-metrics"


@dataclass(frozen=True)
class DailyTestMetric(OpsMetric):
    collection_frequency: ClassVar[GatheringFrequency] = GatheringFrequency.DAILY
    event_name: ClassVar[str] = "daily-metrics"


FuncT = TypeVar("FuncT", bound=Callable[..., Any])


def metrics_uuid(metric_uuid: uuid.UUID) -> Callable[[FuncT], FuncT]:
    def decorator(func_to_decorate: FuncT) -> FuncT:
        @wraps(func_to_decorate)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            print("metric uuid: {}".format(metric_uuid))
            with patch(
                "instance_scheduler.ops_metrics.metrics._get_deployment_uuid"
            ) as solution_id_func:
                solution_id_func.return_value = metric_uuid
                func_to_decorate(*args, **kwargs)

        return cast(FuncT, wrapper)

    return decorator


@patch.dict(environ, {"SEND_METRICS": "False"})
@metrics_uuid(uuid.uuid4())
def test_metrics_not_collected_when_disabled() -> None:
    assert not should_collect_metric(UnlimitedTestMetric(), MockLogger())


@patch.dict(environ, {"SEND_METRICS": "True"})
@metrics_uuid(uuid.uuid4())
def test_unlimited_metric_should_be_sent() -> None:
    assert should_collect_metric(UnlimitedTestMetric, MockLogger())


@patch.dict(environ, {"SEND_METRICS": "True"})
@metrics_uuid(uuid.uuid4())
def test_daily_metric_should_only_be_sent_once_daily() -> None:
    minutes_in_day = 1440
    start_of_day = datetime(2023, 6, 23, 0, 0, 0)

    for interval in [5, 30, 60]:  # test intervals of 5, 30, and 60 minutes
        num_metrics_gathered = 0
        for offset in range(0, minutes_in_day, interval):
            sim_time = start_of_day + timedelta(minutes=offset)
            with patch.dict(
                environ, {"SCHEDULER_FREQUENCY": str(interval)}
            ), freeze_time(sim_time):
                if should_collect_metric(DailyTestMetric, MockLogger()):
                    num_metrics_gathered += 1

        assert (
            num_metrics_gathered == 1
        ), "failed to gather specified number of metrics with interval:{} see output log for uuid used".format(
            interval
        )


@metrics_uuid(uuid.uuid4())
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
    mock_metrics_endpoint: MagicMock, app_env: AppEnv
) -> None:
    with patch(
        "instance_scheduler.ops_metrics.metrics.should_collect_metric"
    ) as should_collect_metric_func:
        should_collect_metric_func.return_value = True
        collect_metric(metric=UnlimitedTestMetric(), logger=MockLogger())

        expected_data = json.dumps(
            {
                "TimeStamp": "2023-06-23 10:00:05",
                "UUID": str(solution_metrics_uuid),
                "Solution": app_env.solution_id,
                "Version": app_env.solution_version,
                "Event_Name": "unlimited-metrics",
                "Context": {},
            },
            indent=0,
        )

        expected_headers = {
            "content-type": "application/json",
            "content-length": str(len(expected_data)),
        }

        mock_metrics_endpoint.assert_called_once_with(
            app_env.anonymous_metrics_url,
            data=expected_data,
            headers=expected_headers,
            timeout=300,
        )


@patch("instance_scheduler.ops_metrics.metrics._deployment_uuid_from_ssm")
def test_deployment_uuid_is_cached(deployment_uuid_func: MagicMock) -> None:
    logger = MockLogger()
    metrics._get_deployment_uuid(logger)
    metrics._get_deployment_uuid(logger)

    assert deployment_uuid_func.call_count == 1
