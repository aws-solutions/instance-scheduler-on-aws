# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from datetime import datetime
from unittest.mock import MagicMock, patch

from instance_scheduler.util import get_boto_config, safe_json
from instance_scheduler.util.app_env import AppEnv


def test_safe_json() -> None:
    safe_json(datetime.now())


@patch("instance_scheduler.util._Config")
def test_get_config(mock_config: MagicMock, app_env: AppEnv) -> None:
    get_boto_config()
    mock_config.assert_called_once_with(
        user_agent_extra=app_env.user_agent_extra,
        retries={"max_attempts": 5, "mode": "standard"},
    )
