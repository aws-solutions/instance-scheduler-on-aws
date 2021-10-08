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
    start new SSM automation document to start or stop RDS clusters.
    Parameters:
    event (dict): event from SSM automation
        example:
            {
                "RdsResourceArns": [
                    "arn:aws:rds:us-east-1:account:cluster:cluster-3d3r",
                    "arn:aws:rds:us-east-1:account:cluster:cluster-1",
                    "arn:aws:rds:us-east-1:account:cluster:cluster-2",
                    "arn:aws:rds:us-east-1:account:cluster:cluster-a1df"

                    ],
                "Action": "start"|"stop"
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
    resource_list = get_resource_list(event.get('RdsResourceArns'))

    for rds_cluster_name in resource_list:
        execution_id = ssm_client.start_automation_execution(
            # Launch SSM Doc via Automation
            DocumentName=event.get('SecondaryAutomationName'),
            Parameters={
                "ClusterName": [
                    rds_cluster_name
                ],
                "Action": [
                    event.get('Action')
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


def get_resource_list(arn_list: list) -> list:
    """ Parse the arn list and return rds db or cluster ids"""
    cluster_separator = ":cluster:"
    cluster_prefix = "cluster-"

    logging.info("Found RDS Cluster list.")
    cluster_ids = split_arn_list(arn_list, cluster_separator)
    # filtering cluster ids for duplicate cluster ids
    return [x for x in cluster_ids if not x.startswith(cluster_prefix)]


def split_arn_list(arn_list, separator):
    resource_ids = []
    for arn in arn_list:
        resource_id = arn.split(separator)[1]
        resource_ids.append(resource_id)
    return resource_ids
