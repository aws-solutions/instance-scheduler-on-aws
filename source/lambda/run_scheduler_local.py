######################################################################################################################
#  Copyright 2019 Amazon.com, Inc. or its affiliates. All Rights Reserved.                                           #
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
import sys
import json

import boto3

import configuration
from main import lambda_handler


def _service_client(service, region=None):
    args = {"service_name": service}
    if region is not None:
        args["region_name"] = region
    return boto3.client(**args)


if __name__ == "__main__":

    if len(sys.argv) < 2:
        print("Enter the name of the stack")
        # noinspection PyCompatibility
        stack = input("Enter name of the Scheduler Stack: ")
    else:
        stack = sys.argv[1]

    try:
        cloudformation_client = _service_client("cloudformation")
        lambda_resource = cloudformation_client.describe_stack_resource(
            StackName=stack, LogicalResourceId="Main").get("StackResourceDetail", None)

        lambda_client = boto3.client("lambda")
        lambda_function = lambda_client.get_function(FunctionName=lambda_resource["PhysicalResourceId"])

        environment = lambda_function["Configuration"]["Environment"]["Variables"]

        for env_var in environment:
            os.environ[env_var] = environment[env_var]

    except Exception as ex:
        print("error setting up environment, {}".format(ex))

    #event = {}
    #with open('sample_events/scheduler_setup_handler_event.json') as json_file:
    #    event = json.load(json_file)

    event = {
        "source": "aws.events",
        "detail-type": "Scheduled Event",
        "resources": ["arn/{}".format(os.getenv(configuration.ENV_SCHEDULER_RULE))]
    }

    lambda_handler(event, None)
