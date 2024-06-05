# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from typing import Any

from instance_scheduler.util.logger import Logger


class MockLogger(Logger):
    def __init__(
        self,
        log_group: str = "",
        log_stream: str = "",
        topic_arn: str = "",
        debug: bool = False,
    ) -> None:
        Logger.__init__(self, log_group="", log_stream="", topic_arn="")

    def info(self, msg: str, *args: Any) -> None:
        s = msg if len(args) == 0 else msg.format(*args)
        print(f"info: {s}")

    def error(self, msg: str, *args: Any) -> None:
        s = msg if len(args) == 0 else msg.format(*args)
        print(f"error: {s}")

    def warning(self, msg: str, *args: Any) -> None:
        s = msg if len(args) == 0 else msg.format(*args)
        print(f"warning: {s}")

    def debug(self, msg: str, *args: Any) -> None:
        s = msg if len(args) == 0 else msg.format(*args)
        print(f"debug: {s}")

    def flush(self) -> None:
        """noop"""
