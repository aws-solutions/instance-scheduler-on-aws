# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0


import json

from instance_scheduler.util.custom_encoder import CustomEncoder
import botocore
import os

ENV_METRICS_URL = "METRICS_URL"
# Solution ID
ENV_SOLUTION_ID = "SOLUTION_ID"
# Send metrics flag
ENV_SEND_METRICS = "SEND_METRICS"
# STACK_ID
STACK_ID = "STACK_ID"
# UUID_KEY
UUID_KEY = "UUID_KEY"
USER_AGENT_EXTRA = "USER_AGENT_EXTRA"


def safe_json(d, indent=0):
    """
    Returns a json document, using a custom encoder that converts all data types not supported by json
    :param d: input dictionary
    :param indent: indent level for output document
    :return: json document for input dictionary
    """
    return json.dumps(d, cls=CustomEncoder, indent=indent)


def as_bool(b):
    s = str(b).lower()
    if s == "true":
        return True
    if s == "false":
        return False
    return None


def get_config():
    # TODO move the user agent string to lambda environment and make it configurable from deployment.
    user_agent_extra_string = os.getenv("USER_AGENT_EXTRA", "AwsSolution/SO0030/v1.5.0")
    solution_config = {
        "user_agent_extra": user_agent_extra_string,
        "retries": {"max_attempts": 5, "mode": "standard"},
    }
    return botocore.config.Config(**solution_config)
