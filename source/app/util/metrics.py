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

import os
import uuid
from datetime import datetime

import requests


import util
from util import safe_json
from version import VERSION
import boto3
#from botocore.exceptions import ClientError
import botocore

INF_METRICS_DATA = "Sending anonymous metrics data: {}"
INF_METRICS_DATA_SENT = "Metrics data send, status code is {}, message is {}"
WARN_ENV_METRICS_URL_NOT_SET = "Environment variable {} is not set, metrics dat is not sent"
WARN_SENDING_METRICS_FAILED = "Failed send metrics data ({})"
WARN_SOLUTION_ID_NOT_SET = "Solution id is not set, metrics are not sent"


def allow_send_metrics():
    return str(os.getenv(util.ENV_SEND_METRICS, "false")).lower() == "true"


def send_metrics_data(metrics, logger):
    """
    Sends metrics data
    :param metrics: metrics data
    :param logger: logger
    :return:
    """
    try:
        url = os.getenv(util.ENV_METRICS_URL, None)
        if url is None:
            logger.warning(WARN_ENV_METRICS_URL_NOT_SET, util.ENV_METRICS_URL)
            return

        solution_id = os.getenv(util.ENV_SOLUTION_ID, None)
        if solution_id is None:
            logger.warning(WARN_SOLUTION_ID_NOT_SET)
            return
        if solution_id is None:
            logger.warning(WARN_SOLUTION_ID_NOT_SET)
            return

        stackId = os.getenv(util.STACK_ID, None)[-36:]
        uuid_key = os.getenv(util.UUID_KEY) + str(stackId)
        user_agent_extra_string = os.getenv(util.USER_AGENT_EXTRA)
        try:
            if user_agent_extra_string is not None:
                solution_config = {"user_agent_extra": user_agent_extra_string}
                config = botocore.config.Config(**solution_config)
            else:
                config = None

            client = boto3.client("ssm", config=config)
            response = client.get_parameter(
                Name=uuid_key
            )
            uuid_parameter = response.get("Parameter", {}).get("Value")
        except botocore.exceptions.ClientError as ex:
            if ex.response.get("Error", {}).get("Code") == "ParameterNotFound":
                uuid_parameter = str(uuid.uuid4())
                try:
                    logger.info("creating a new parameter")
                    client.put_parameter(
                        Name=uuid_key,
                        Description="This is a unique id for each aws-instance-scheduler solution stack, for reporting metrics.",
                        Value=uuid_parameter,
                        Type="String"
                    )
                except Exception as ex:
                    logger.info("Failed to create a new parameter")
                    logger.info(ex)
            else:
                logger.warning("Error creating UUID parameter.")
        
        logger.info("uuid_parameter {} ".format(uuid_parameter))
        data_dict = {
            "TimeStamp": str(datetime.utcnow().isoformat()),
            "UUID": uuid_parameter,
            "Data": metrics,
            "Solution": solution_id,
            "Version" : VERSION
        }

        data_json = safe_json(data_dict, indent=3)
        logger.info(INF_METRICS_DATA, data_json)

        headers = {
            'content-type': 'application/json',
            "content-length": str(len(data_json))
        }

        response = requests.post(url, data=data_json, headers=headers, timeout=300)
        response.raise_for_status()
        logger.debug(INF_METRICS_DATA_SENT, response.status_code, response.text)
    except Exception as exc:
        logger.warning((WARN_SENDING_METRICS_FAILED.format(str(exc))))
