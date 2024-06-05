# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import os
from dataclasses import dataclass
from unittest.mock import patch

from instance_scheduler.handler.environments.metrics_uuid_environment import (
    MetricsUuidEnvironment,
)


@dataclass
class MockMetricsUuidEnviron(MetricsUuidEnvironment):
    user_agent_extra: str = "user-agent-extra"
    uuid_key: str = "my-uuid-key"
    stack_id: str = "my-stack-id"

    def _to_env_dict(self) -> dict[str, str]:
        return {
            "USER_AGENT_EXTRA": self.user_agent_extra,
            "STACK_ID": self.stack_id,
            "UUID_KEY": self.uuid_key,
        }

    def __enter__(self) -> "MockMetricsUuidEnviron":
        self._patcher = patch.dict(os.environ, self._to_env_dict())
        self._patcher.__enter__()
        return self

    def __exit__(self, exc_type: None, exc_val: None, exc_tb: None) -> None:
        self._patcher.__exit__()
