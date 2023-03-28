######################################################################################################################
#  Copyright 2021 Amazon.com, Inc. or its affiliates. All Rights Reserved.                                           #
#                                                                                                                    #
#  Licensed under the Apache License Version 2.0 (the "License"). You may not use this file except in compliance     #
#  with the License. A copy of the License is located at                                                             #
#                                                                                                                    #
#      http://www.apache.org/licenses/                                                                               #
#                                                                                                                    #
#  or in the "license" file accompanying this file. This file is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES #
#  OR CONDITIONS OF ANY KIND, express or implied. See the License for the specific language governing permissions    #
#  and limitations under the License.                                                                                #
######################################################################################################################

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
