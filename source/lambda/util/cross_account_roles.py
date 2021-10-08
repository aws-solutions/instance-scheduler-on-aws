###############################################################################
#  Copyright 2021 Amazon.com, Inc. or its affiliates. All Rights Reserved.    #
#                                                                             #
#  Licensed under the Apache License, Version 2.0 (the "License").            #
#  You may not use this file except in compliance with the License.
#  A copy of the License is located at                                        #
#                                                                             #
#      http://www.apache.org/licenses/LICENSE-2.0                             #
#                                                                             #
#  or in the "license" file accompanying this file. This file is distributed  #
#  on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, express #
#  or implied. See the License for the specific language governing permissions#
#  and limitations under the License.                                         #
###############################################################################

import os


def get_cross_account_role_arn(accounts: list) -> list:
    """
    param: AWS account list
    return: List of ARN for each account
    """
    account_arns = []
    for account in accounts:
        partition = os.getenv('aws_partition')
        namespace = os.getenv('namespace')
        role_name = os.getenv('execution_role_name')
        region = os.getenv('AWS_REGION')
        arn = f"arn:{partition}:iam::{account}:role/{namespace}-{role_name}-{region}"
        account_arns.append(arn)
    return account_arns
