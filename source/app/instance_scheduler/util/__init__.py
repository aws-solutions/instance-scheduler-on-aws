# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import json as _json
from typing import Any as _Any

from botocore.config import Config as _Config

from instance_scheduler.util.app_env import get_app_env as _get_app_env
from instance_scheduler.util.custom_encoder import CustomEncoder as _CustomEncoder


def safe_json(d: _Any, indent: int = 0) -> str:
    """
    Returns a json document, using a custom encoder that converts all data types not supported by json
    :param d: input dictionary
    :param indent: indent level for output document
    :return: json document for input dictionary
    """
    return _json.dumps(d, cls=_CustomEncoder, indent=indent)


def get_boto_config() -> _Config:
    """Returns a boto3 config with standard retries and `user_agent_extra`"""
    return _Config(
        retries={"max_attempts": 5, "mode": "standard"},
        user_agent_extra=_get_app_env().user_agent_extra,
    )
