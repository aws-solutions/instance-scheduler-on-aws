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

import boto3
import json
from functools import lru_cache

@lru_cache(maxsize=1)
def get_lambda_client():
    return boto3.client("lambda")

def get_lambda_env_variables(lambda_function_physical_resource_id):
    try:
        lambda_function = get_lambda_client().get_function(FunctionName=lambda_function_physical_resource_id)
        env_variables = lambda_function["Configuration"]["Environment"]["Variables"]
        return env_variables
    except Exception as e:
        print(f'Failed to retrieve environment variables. Exception: {e}')
        return None

def invoke_lambda_function(function_name, event):
    try:
        response = get_lambda_client().invoke(
            FunctionName=function_name,
            InvocationType='RequestResponse',
            LogType='Tail',
            Payload=json.dumps(event))
        print (f'Lambda function [{function_name}] invoke response: {response}')
    except Exception as e:
        print(f'Failed to execute lambda. Exception: {e}')
        return None

