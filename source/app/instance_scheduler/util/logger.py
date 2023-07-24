# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import time
from types import TracebackType
from typing import TYPE_CHECKING, Any, Optional

from instance_scheduler import boto_retry

if TYPE_CHECKING:
    from mypy_boto3_logs.client import CloudWatchLogsClient
    from mypy_boto3_logs.type_defs import PutLogEventsRequestRequestTypeDef
    from mypy_boto3_sns.client import SNSClient
else:
    CloudWatchLogsClient = object
    SNSClient = object
    PutLogEventsRequestRequestTypeDef = object

LOG_MAX_BATCH_SIZE = 1048576
LOG_ENTRY_ADDITIONAL = 26


class Logger:
    def __init__(
        self,
        *,
        log_group: str,
        log_stream: str,
        topic_arn: str,
        debug: bool = False,
    ) -> None:
        self._log_group = log_group
        self._log_stream = log_stream
        self._topic_arn = topic_arn
        self._debug = debug
        self._buffer_size = 60 if self._debug else 30
        self._buffer: list[tuple[int, str]] = []
        self._cached_size = 0
        self._client: Optional[CloudWatchLogsClient] = None
        self._sns: Optional[SNSClient] = None

    def __enter__(self) -> "Logger":
        return self

    def __exit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc_value: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> None:
        self.flush()

    def _emit(self, level: str, msg: str, *args: Any) -> str:
        s = msg if len(args) == 0 else msg.format(*args)
        t = time.time()
        s = "{:7s} : {}".format(level, s)

        if self._cached_size + (len(s) + LOG_ENTRY_ADDITIONAL) > LOG_MAX_BATCH_SIZE:
            self.flush()

        self._cached_size += len(s) + LOG_ENTRY_ADDITIONAL

        self._buffer.append((int(t * 1000), s))

        if len(self._buffer) >= self._buffer_size:
            self.flush()

        return s

    @property
    def sns(self) -> SNSClient:
        if self._sns is None:
            self._sns = boto_retry.get_client_with_standard_retry("sns")
        return self._sns

    def publish_to_sns(self, level: str, msg: str) -> None:
        """
        Publish message to sns topic
        :param msg:
        :param level:
        :return:
        """
        message = "Loggroup: {}\nLogstream {}\n{} : {}".format(
            self._log_group, self._log_stream, level, msg
        )
        self.sns.publish(TopicArn=self._topic_arn, Message=message)

    def info(self, msg: str, *args: Any) -> None:
        """
        Logs informational message
        :param msg: Message format string
        :param args: Message parameters
        :return:
        """
        self._emit("INFO", msg, *args)

    def error(self, msg: str, *args: Any) -> None:
        """
        Logs error message
        :param msg: Error message format string
        :param args: parameters
        :return:
        """
        s = self._emit("ERROR", msg, *args)
        self.publish_to_sns("Error", s)

    def warning(self, msg: str, *args: Any) -> None:
        """
        Logs warning message
        :param msg: Warning message format string
        :param args: parameters
        :return:
        """
        s = self._emit("WARNING", msg, *args)
        self.publish_to_sns("Warning", s)

    def debug(self, msg: str, *args: Any) -> None:
        """
        Conditionally logs debug message, does not log if debugging is disabled
        :param msg: Debug message format string
        :param args: parameters
        :return:
        """
        if self._debug:
            self._emit("DEBUG", msg, *args)

    @property
    def client(self) -> CloudWatchLogsClient:
        if self._client is None:
            self._client = boto_retry.get_client_with_standard_retry("logs")
        return self._client

    def flush(self) -> None:
        """
        Writes all buffered messages to CloudWatch Stream
        :return:
        """

        if len(self._buffer) == 0:
            return

        put_event_args: PutLogEventsRequestRequestTypeDef = {
            "logGroupName": self._log_group,
            "logStreamName": self._log_stream,
            "logEvents": [{"timestamp": r[0], "message": r[1]} for r in self._buffer],
        }

        retries = 5
        while retries > 0:
            try:
                self.client.put_log_events(**put_event_args)
                self._buffer = []
                self._cached_size = 0
                return
            except self.client.exceptions.ResourceNotFoundException:
                retries -= 1
                self.client.create_log_stream(
                    logGroupName=self._log_group, logStreamName=self._log_stream
                )
            except Exception:
                return
