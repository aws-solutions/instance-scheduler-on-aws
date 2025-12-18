# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import dataclasses
from datetime import datetime, timezone
from os import environ
from typing import Final, Optional
from uuid import UUID

from aws_lambda_powertools import Logger
from instance_scheduler.ops_metrics.anonymous_metric_wrapper import (
    AnonymousMetricWrapper,
)
from instance_scheduler.ops_metrics.metric_type.ops_metric import OpsMetric
from instance_scheduler.util import safe_json
from instance_scheduler.util.app_env_utils import AppEnvError, env_to_bool
from urllib3 import BaseHTTPResponse, PoolManager


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
    hub_account_id: str

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
                hub_account_id=environ["HUB_ACCOUNT_ID"],
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
    metric: OpsMetric, logger: Logger
) -> Optional[AnonymousMetricWrapper]:
    if not should_collect_metric():
        return None

    try:
        metrics_env = get_metrics_env()
        url = metrics_env.anonymous_metrics_url

        metric_wrapper = AnonymousMetricWrapper(
            # current required timestamp format for metrics backend (7/11/23)
            timestamp=str(datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")),
            uuid=str(metrics_env.metrics_uuid),
            hub_account_id=get_metrics_env().hub_account_id,
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

        response: BaseHTTPResponse = http.request(
            "POST", url, headers=headers, body=data_json
        )
        logger.debug(f"Metrics data sent, status code is {response.status}")
        return metric_wrapper
    except Exception as exc:
        logger.warning(f"Failed sending metrics data ({str(exc)})")
        return None


def should_collect_metric() -> bool:
    try:
        env: Final = get_metrics_env()
    except AppEnvError:
        # environment not configured, treat as disabled
        return False
    if not env.send_anonymous_metrics:
        # do not send metrics when not enabled
        return False

    return True
