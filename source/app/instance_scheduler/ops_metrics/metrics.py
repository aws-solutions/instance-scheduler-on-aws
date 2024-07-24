# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import dataclasses
from datetime import datetime, timezone
from os import environ
from typing import Final, Optional, assert_never
from uuid import UUID

from aws_lambda_powertools import Logger as PowerToolsLogger
from urllib3 import HTTPResponse, PoolManager

from instance_scheduler.ops_metrics import GatheringFrequency
from instance_scheduler.ops_metrics.anonymous_metric_wrapper import (
    AnonymousMetricWrapper,
)
from instance_scheduler.ops_metrics.metric_type.ops_metric import OpsMetric
from instance_scheduler.util import safe_json
from instance_scheduler.util.app_env_utils import AppEnvError, env_to_bool
from instance_scheduler.util.logger import Logger


@dataclasses.dataclass
class MetricsEnvironment:
    # a sub environment that controls anonymized metrics
    # the absense/misconfiguration of this environment should not be a solution-breaking
    # error but should rather just disable the sending of metrics
    send_anonymous_metrics: bool
    anonymous_metrics_url: str
    solution_id: str
    solution_version: str
    scheduler_frequency_minutes: int
    metrics_uuid: UUID

    @staticmethod
    def from_env() -> "MetricsEnvironment":
        try:
            try:
                metrics_uuid = UUID(environ["METRICS_UUID"])
            except ValueError:
                raise AppEnvError(f"invalid METRICS_UUID: {environ['METRICS_UUID']}")

            try:
                scheduler_frequency_minutes = int(
                    environ["SCHEDULING_INTERVAL_MINUTES"]
                )
            except ValueError:
                raise AppEnvError(
                    f"invalid SCHEDULING_INTERVAL_MINUTES: {environ['SCHEDULING_INTERVAL_MINUTES']}"
                )

            return MetricsEnvironment(
                send_anonymous_metrics=env_to_bool(environ["SEND_METRICS"]),
                anonymous_metrics_url=environ["METRICS_URL"],
                solution_id=environ["SOLUTION_ID"],
                solution_version=environ["SOLUTION_VERSION"],
                scheduler_frequency_minutes=scheduler_frequency_minutes,
                metrics_uuid=metrics_uuid,
            )

        except KeyError as err:
            raise AppEnvError(
                f"Missing required application environment variable: {err.args[0]}"
            ) from err


http = PoolManager()

_metrics_env: Optional[MetricsEnvironment] = None


def get_metrics_env() -> MetricsEnvironment:
    """can raise AppEnvError"""
    global _metrics_env
    if not _metrics_env:
        _metrics_env = MetricsEnvironment.from_env()  # can raise AppEnvError
    return _metrics_env


def collect_metric(
    metric: OpsMetric, logger: Logger | PowerToolsLogger
) -> Optional[AnonymousMetricWrapper]:
    if not should_collect_metric(metric):
        return None

    try:
        metrics_env = get_metrics_env()
        url = metrics_env.anonymous_metrics_url

        metric_wrapper = AnonymousMetricWrapper(
            # current required timestamp format for metrics backend (7/11/23)
            timestamp=str(datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")),
            uuid=str(metrics_env.metrics_uuid),
            solution=get_metrics_env().solution_id,
            version=get_metrics_env().solution_version,
            event_name=metric.event_name,
            context_version=metric.context_version,
            context=metric,
        )

        data_json = safe_json(dataclasses.asdict(metric_wrapper))
        logger.info(f"Sending anonymous metrics data: {data_json}")

        headers = {
            "content-type": "application/json",
            "content-length": str(len(data_json)),
        }

        response: HTTPResponse = http.request(  # type: ignore[no-untyped-call]
            "POST", url, headers=headers, body=data_json
        )
        logger.debug(f"Metrics data sent, status code is {response.status}")
        return metric_wrapper
    except Exception as exc:
        logger.warning(("Failed sending metrics data ({})".format(str(exc))))
        return None


def should_collect_metric(metric: OpsMetric | type[OpsMetric]) -> bool:
    try:
        env: Final = get_metrics_env()
    except AppEnvError:
        # environment not configured, treat as disabled
        return False
    if not env.send_anonymous_metrics:
        # do not send metrics when not enabled
        return False

    solution_uuid = env.metrics_uuid
    interval = env.scheduler_frequency_minutes
    current_time = datetime.now(timezone.utc)

    if metric.collection_frequency is GatheringFrequency.UNLIMITED:
        return True
    elif metric.collection_frequency is GatheringFrequency.DAILY:
        return _is_allowed_hour_for_metrics(
            solution_uuid, current_time
        ) and _is_first_call_in_current_hour(current_time, interval)
    elif metric.collection_frequency is GatheringFrequency.WEEKLY:
        return (
            _is_first_day_in_week(current_time)
            and _is_allowed_hour_for_metrics(solution_uuid, current_time)
            and _is_first_call_in_current_hour(current_time, interval)
        )
    else:
        assert_never(metric.collection_frequency)


def _is_first_day_in_week(current_time: datetime) -> bool:
    return current_time.weekday() == 0


def _is_allowed_hour_for_metrics(solution_uuid: UUID, current_time: datetime) -> bool:
    hour_to_send = solution_uuid.int % 20
    return current_time.hour == hour_to_send


def _is_first_call_in_current_hour(
    current_time: datetime, scheduling_frequency: int
) -> bool:
    return current_time.minute < scheduling_frequency
