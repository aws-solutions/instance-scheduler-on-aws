# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import os
from dataclasses import dataclass
from unittest.mock import patch
from zoneinfo import ZoneInfo


@dataclass
class TestSuiteEnv:
    log_group: str = "my-log-group"
    topic_arn: str = "arn:aws:sns:us-east-1:123456789012:my-topic-arn"
    user_agent_extra: str = "my-user-agent-extra"
    default_timezone: ZoneInfo = ZoneInfo("Asia/Tokyo")
    maintenance_window_table_name: str = "my-maintenance-window-table"
    config_table_name: str = "my-config-table-name"
    state_table_name: str = "my-state-table-name"

    def _to_env_dict(self) -> dict[str, str]:
        return {
            "USER_AGENT_EXTRA": self.user_agent_extra,
            "DEFAULT_TIMEZONE": str(self.default_timezone),
        }

    def __enter__(self) -> "TestSuiteEnv":
        self._patcher = patch.dict(os.environ, self._to_env_dict())
        self._patcher.__enter__()
        return self

    def __exit__(self, exc_type: None, exc_val: None, exc_tb: None) -> None:
        self._patcher.__exit__()
