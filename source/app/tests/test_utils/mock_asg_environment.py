# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import os
from dataclasses import dataclass
from unittest.mock import patch
from zoneinfo import ZoneInfo


@dataclass
class MockAsgEnvironment:
    user_agent_extra: str = "my-user-agent-extra"
    issues_topic_arn: str = "arn:aws:sns:us-east-1:123456789012:my-topic-arn"
    logger_raise_exceptions: bool = False
    config_table_name: str = "my-config-table-name"
    asg_scheduling_role_name: str = "my-role"
    default_timezone: ZoneInfo = ZoneInfo("UTC")
    schedule_tag_key: str = "Schedule"
    scheduled_tag_key: str = "scheduled"
    rule_prefix: str = "is-"

    def _to_env_dict(self) -> dict[str, str]:
        return {
            "USER_AGENT_EXTRA": self.user_agent_extra,
            "ISSUES_TOPIC_ARN": self.issues_topic_arn,
            "LOGGER_RAISE_EXCEPTIONS": str(self.logger_raise_exceptions),
            "CONFIG_TABLE": self.config_table_name,
            "ASG_SCHEDULING_ROLE_NAME": self.asg_scheduling_role_name,
            "DEFAULT_TIMEZONE": str(self.default_timezone),
            "SCHEDULE_TAG_KEY": self.schedule_tag_key,
            "SCHEDULED_TAG_KEY": self.scheduled_tag_key,
            "RULE_PREFIX": self.rule_prefix,
        }

    def __enter__(self) -> "MockAsgEnvironment":
        self._patcher = patch.dict(os.environ, self._to_env_dict())
        self._patcher.__enter__()
        return self

    def __exit__(self, exc_type: None, exc_val: None, exc_tb: None) -> None:
        self._patcher.__exit__()
