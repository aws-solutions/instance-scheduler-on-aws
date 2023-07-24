# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from typing import Any

from instance_scheduler.util.logger import Logger


class MockLogger(Logger):
    def __init__(self) -> None:
        Logger.__init__(self, log_group="", log_stream="", topic_arn="")

    def info(self, _: str, *__: Any) -> None:
        """noop"""

    def error(self, _: str, *__: Any) -> None:
        """noop"""

    def warning(self, _: str, *__: Any) -> None:
        """noop"""

    def debug(self, _: str, *__: Any) -> None:
        """noop"""

    def flush(self) -> None:
        """noop"""
