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

import boto
import botocore

def get_config():
    user_agent_extra_string = os.getenv("USER_AGENT_EXTRA", "AwsSolution/SO0030/v1.5.0")
    solution_config = {"user_agent_extra": user_agent_extra_string, "retries": {'max_attempts': 5, 'mode': 'standard'}}
    return botocore.config.Config(**solution_config) 

# def get_client(service, context=None, session=None):

