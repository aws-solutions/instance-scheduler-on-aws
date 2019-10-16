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
import time
from functools import lru_cache

@lru_cache(maxsize=1)
def get_rts_client():
    return boto3.client("sts")

@lru_cache(maxsize=1)
def get_assume_role_credentials(role_arn):
    try:
        assume_role = get_rts_client().assume_role(
            RoleArn=role_arn,
            RoleSessionName='is-122-remote-session'
        )
        return assume_role["Credentials"]
    except Exception as e:
        print(f'Failed to retrieve assume role credentials. Exception: {e}')
        return None
