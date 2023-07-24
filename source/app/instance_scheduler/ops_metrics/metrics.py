# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import dataclasses
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

import boto3
import requests
from botocore.exceptions import ClientError
from typing_extensions import assert_never

from instance_scheduler.ops_metrics import GatheringFrequency
from instance_scheduler.ops_metrics.anonymous_metric_wrapper import (
    AnonymousMetricWrapper,
)
from instance_scheduler.ops_metrics.metric_type.ops_metric import OpsMetric
from instance_scheduler.util import get_boto_config, safe_json
from instance_scheduler.util.app_env import get_app_env
from instance_scheduler.util.logger import Logger

if TYPE_CHECKING:
    from mypy_boto3_ssm.client import SSMClient
else:
    SSMClient = object


def collect_metric(
    metric: OpsMetric, logger: Logger
) -> Optional[AnonymousMetricWrapper]:
    if not should_collect_metric(metric, logger):
        return None

    try:
        app_env = get_app_env()
        url = app_env.anonymous_metrics_url

        metric_wrapper = AnonymousMetricWrapper(
            # current required timestamp format for metrics backend (7/11/23)
            TimeStamp=str(datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")),
            UUID=str(_get_deployment_uuid(logger)),
            Solution=app_env.solution_id,
            Version=app_env.solution_version,
            Event_Name=metric.event_name,
            Context=metric,
        )

        data_json = safe_json(dataclasses.asdict(metric_wrapper))
        logger.info("Sending anonymous metrics data: {}", data_json)

        headers = {
            "content-type": "application/json",
            "content-length": str(len(data_json)),
        }

        response = requests.post(url, data=data_json, headers=headers, timeout=300)
        response.raise_for_status()
        logger.debug(
            "Metrics data sent, status code is {}, message is {}",
            response.status_code,
            response.text,
        )
        return metric_wrapper
    except Exception as exc:
        logger.warning(("Failed sending metrics data ({})".format(str(exc))))
        return None


# cache the deployment uuid to try to minimize calls to ssm
_deployment_uuid: Optional[uuid.UUID] = None


def _get_deployment_uuid(logger: Logger) -> uuid.UUID:
    global _deployment_uuid
    if not _deployment_uuid:
        _deployment_uuid = _deployment_uuid_from_ssm(logger)
    return _deployment_uuid


def _deployment_uuid_from_ssm(logger: Logger) -> uuid.UUID:
    app_env = get_app_env()
    stack_id = app_env.stack_id[-36:]
    uuid_key = app_env.uuid_key + str(stack_id)
    ssm: SSMClient = boto3.client("ssm", config=get_boto_config())
    try:
        ssm_response = ssm.get_parameter(Name=uuid_key)
        uuid_parameter = ssm_response.get("Parameter", {}).get("Value")
        return uuid.UUID(uuid_parameter)
    except ClientError as fetch_exception:
        if fetch_exception.response.get("Error", {}).get("Code") == "ParameterNotFound":
            uuid_parameter = str(uuid.uuid4())
            try:
                logger.info("creating a new parameter")
                ssm.put_parameter(
                    Name=uuid_key,
                    Description="This is a unique id for each Instance Scheduler on AWS solution stack, for reporting metrics.",
                    Value=uuid_parameter,
                    Type="String",
                )
                return uuid.UUID(uuid_parameter)
            except Exception as create_exception:
                logger.info(
                    "Unable to create UUID for operational metrics, metrics will not be sent: \n{}".format(
                        create_exception
                    )
                )
                raise ValueError("Unable to get solution UUID")
        else:
            logger.info(
                "Unable to fetch UUID for operational metrics, metrics will not be sent: \n{}".format(
                    fetch_exception
                )
            )
            raise ValueError("Unable to get solution UUID")


def should_collect_metric(metric: OpsMetric | type[OpsMetric], logger: Logger) -> bool:
    app_env = get_app_env()
    if not app_env.send_anonymous_metrics:
        # do not send metrics when not enabled
        return False

    try:
        solution_uuid = _get_deployment_uuid(logger)  # can fail
        interval = app_env.scheduler_frequency_minutes
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
    except ValueError:
        return False


def _is_first_day_in_week(current_time: datetime) -> bool:
    return current_time.weekday() == 0


def _is_allowed_hour_for_metrics(
    solution_uuid: uuid.UUID, current_time: datetime
) -> bool:
    hour_to_send = solution_uuid.int % 20
    return current_time.hour == hour_to_send


def _is_first_call_in_current_hour(
    current_time: datetime, scheduling_frequency: int
) -> bool:
    return current_time.minute < scheduling_frequency
