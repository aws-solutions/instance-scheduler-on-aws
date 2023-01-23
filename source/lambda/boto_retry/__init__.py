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

import boto3
import botocore.config

def get_client_with_standard_retry(service_name, region=None, session=None):
    """
    Creates a bot3 client for the specified service name and region. The return client will have additional method for the
    specified methods that are wrapped with the logic of the specified wait strategy or the default strategy for that service.
    The method names must be valid for the boto3 service client. The name of the added functions is the name of the original
    function plus the (default) value of method_suffix parameter
    :param service_name: Name of the service
    :param region: Region for the client
    :param session: Boto3 session, if None a new session will be created
    :return: Client for the service with additional method that use retry logic
    """
    args = {
        "service_name": service_name,
    }

    if region is not None:
        args["region_name"] = region

    user_agent_extra_string = os.getenv("USER_AGENT_EXTRA", None)

    retries = {
        'max_attempts': 5,
        'mode': 'standard'
    }
    if user_agent_extra_string is not None:
        solution_config = {"user_agent_extra": user_agent_extra_string, "retries": retries}
        config = botocore.config.Config(**solution_config) 
        args["config"] = config

    aws_session = session if session is not None else boto3.Session()

    result = aws_session.client(**args)

    return result