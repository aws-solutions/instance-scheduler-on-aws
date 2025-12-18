# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import logging
from enum import Enum

from aws_lambda_powertools import Logger


def should_log_events(logger: Logger) -> bool:
    return logger.log_level <= logging.DEBUG


def powertools_logger(service: str = "instance-scheduler") -> Logger:
    silence_boto_logs()
    logger = Logger(
        use_rfc3339=True,
        log_uncaught_exceptions=True,
        service=service,
    )
    return logger


def silence_boto_logs() -> None:
    logging.getLogger("boto3").setLevel(logging.WARN)
    logging.getLogger("botocore").setLevel(logging.WARN)
    logging.getLogger("nose").setLevel(logging.WARN)
    logging.getLogger("s3transfer").setLevel(logging.WARN)
    logging.getLogger("urllib3").setLevel(logging.WARN)


class LogContext(str, Enum):
    REGISTRATION = "registration"
