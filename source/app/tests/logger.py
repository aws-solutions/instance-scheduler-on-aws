# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from typing import Any

from aws_lambda_powertools import Logger


class MockLogger(Logger):
    def info(self, msg: str, *args: Any) -> None:  # type: ignore
        s = msg if len(args) == 0 else msg.format(*args)
        print(f"info: {s}")

    def error(self, msg: str, *args: Any) -> None:  # type: ignore
        s = msg if len(args) == 0 else msg.format(*args)
        print(f"error: {s}")

    def warning(self, msg: str, *args: Any) -> None:  # type: ignore
        s = msg if len(args) == 0 else msg.format(*args)
        print(f"warning: {s}")

    def debug(self, msg: str, *args: Any) -> None:  # type: ignore
        s = msg if len(args) == 0 else msg.format(*args)
        print(f"debug: {s}")
