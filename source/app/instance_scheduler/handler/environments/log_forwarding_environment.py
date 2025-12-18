# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class LogForwardingEnvironment:
    sns_notification_topic: str

    @classmethod
    def from_env(cls) -> "LogForwardingEnvironment":
        return cls(
            sns_notification_topic=os.environ["SNS_NOTIFICATION_TOPIC"],
        )
