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

import boto3
import logging
from botocore.config import Config


def start_rds_secondary_ssm_automation(event, context) -> list:
    """
    start new SSM automation document to start or stop RDS instances.
    Parameters:
    event (dict): event from SSM automation
        example:
            {
                "RdsResourceArns": [
                    "arn:aws:rds:us-east-1:account:db:database-name-1",
                    "arn:aws:rds:us-east-1:account:db:database-name-2"
                    ],
                "Region": "us-east-1",
                "SecondaryAutomationName": "secondary-automation-name",
                "SolutionId": "SO0030",
                "SolutionVersion": "v2.0.0",
                "ExecutionRoleArn": "arn:aws:iam::account:role/role-name"
            }
    context (dict): context object

    Returns:
    list : list of secondary execution ids

   """
    logging.debug(context)
    execution_ids = []
    # handle empty arn list
    if not event.get('RdsResourceArns'):
        return execution_ids

    ssm_client = get_client(event)
    resource_list = split_arn_list(event.get('RdsResourceArns'))

    for rds_instance_id in resource_list:
        execution_id = ssm_client.start_automation_execution(
            # Launch SSM Doc via Automation
            DocumentName=event.get('SecondaryAutomationName'),
            Parameters={
                "InstanceId": [
                    rds_instance_id
                ],
                "AutomationAssumeRole": [
                    event.get('ExecutionRoleArn')
                ]
            }
        )['AutomationExecutionId']
        execution_ids.append(execution_id)

    return execution_ids


def get_client(event):
    """Create Boto3 client for SSM service"""
    boto_config = Config(
        user_agent_extra=f'AwsSolution/{event.get("SolutionId")}/'
                         f'{event.get("SolutionVersion")}',
        retries={
            'mode': 'standard'
        }
    )

    return boto3.client('ssm',
                        region_name=event.get('Region'),
                        config=boto_config)


def split_arn_list(arn_list):
    separator = ':db:'
    resource_ids = []
    for arn in arn_list:
        resource_id = arn.split(separator)[1]
        resource_ids.append(resource_id)
    return resource_ids
