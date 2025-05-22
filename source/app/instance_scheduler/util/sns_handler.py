# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from logging import WARNING, Handler, LogRecord
from typing import TYPE_CHECKING, Final

from instance_scheduler import boto_retry

if TYPE_CHECKING:
    from mypy_boto3_sns.client import SNSClient
else:
    SNSClient = object


class SnsHandler(Handler):  # NOSONAR
    def __init__(
        self,
        *,
        topic_arn: str,
        log_group_name: str,
        log_stream_name: str,
        raise_exceptions: bool = False
    ) -> None:
        super().__init__(level=WARNING)

        self._sns: Final[SNSClient] = boto_retry.get_client_with_standard_retry("sns")
        self._topic_arn: Final = topic_arn
        self._log_group: Final = log_group_name
        self._log_stream: Final = log_stream_name
        self._raise_exceptions: Final = raise_exceptions

    def emit(self, record: LogRecord) -> None:
        try:
            message: Final = "Loggroup: {}\nLogstream {}\n{} : {}".format(
                self._log_group, self._log_stream, record.levelname, record.getMessage()
            )
            self._sns.publish(TopicArn=self._topic_arn, Message=message)
        except Exception:
            if self._raise_exceptions:
                raise
