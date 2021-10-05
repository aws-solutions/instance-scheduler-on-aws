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
from util import get_config
import os
import schedulers
import json


class SSMHandler:

    """
    Initialize the SSMHandler class, the class enables to start/stop ec2
    instances, rds instances, rds clusters.
    :param logger - logger value initialized to send log events to a specific
        log stream, refer util.logger
    :param accounts - list of account ids 
    :param regions - list of regions
    :param automation_assume_role_arn- the iam role used to initiate the runbook
    :param execution_role_name - the iam role name in the target accounts
    """

    def __init__(self, logger, accounts, regions, automation_assume_role_arn,
                 execution_role_name, started_tags, stopped_tags):
        self._logger = logger
        self.ssm_client = boto3.client('ssm', config=get_config())
        self.accounts = accounts
        self.regions = regions
        self.automation_assume_role_arn = automation_assume_role_arn
        self.execution_role_name = execution_role_name
        self.resource_tag_map_list = []
        self.started_tags = started_tags
        self.stopped_tags = stopped_tags
        self.max_allowed_accounts_in_ssm_api = os.getenv(
            schedulers.MAX_ALLOWED_ACCOUNTS_IN_SSM_API, 50)
        self.max_concurrency = os.getenv(schedulers.SSM_MAX_CONCURRENCY, '100%')
        self.max_errors = os.getenv(schedulers.SSM_MAX_ERRORS, '100%')

    def get_tags_in_json_formatted_string(self, ssm_runbook_name, tags):
        if len(tags) > 0 and ssm_runbook_name in [schedulers.EC2_START_SSM_DOC,
                                                  schedulers.EC2_STOP_SSM_DOC]:
            return [json.dumps(tag) for tag in tags]
        elif len(tags) > 0 and ssm_runbook_name in [schedulers.RDS_CLUSTERS_START_SSM_DOC,
                                                    schedulers.RDS_CLUSTERS_STOP_SSM_DOC,
                                                    schedulers.RDS_INSTANCES_START_SSM_DOC,
                                                    schedulers.RDS_INSTANCES_STOP_SSM_DOC]:
            tags_as_map_list = {}
            for tag in tags:
                tags_as_map_list[tag.get('Key')] = tag.get('Value')
            return [json.dumps(tags_as_map_list)]
        elif len(tags) <= 0 and ssm_runbook_name in [schedulers.EC2_START_SSM_DOC,
                                                     schedulers.EC2_STOP_SSM_DOC]:
            return [json.dumps({
                "Key": "StateChanged",
                "Value": "Resource started by Instance Scheduler"
            })]
        elif len(tags) <= 0 and ssm_runbook_name in [schedulers.RDS_CLUSTERS_START_SSM_DOC,
                                                    schedulers.RDS_CLUSTERS_STOP_SSM_DOC,
                                                    schedulers.RDS_INSTANCES_START_SSM_DOC,
                                                    schedulers.RDS_INSTANCES_STOP_SSM_DOC]:
            return [json.dumps({
                "StateChanged": "Resource started by Instance Scheduler"
                })]
        else:
            self._logger.info(f"Tags are applied in different format for each runbook, the runbook {ssm_runbook_name} is not part of the runbooks defined by the solutions. \
             No tag formatting is found.")
            return []

    def execute_ssm_api(self, ssm_runbook_name,
                        schedule_tag_name,
                        schedule_tag_value,
                        tags=[],
                        target_locations=[]):
        """
        This method will only be used internally by run_ssm_runbook,
        which will split up
        requests to SSM API "start_automation_execution" by splitting up the
        accounts into a list of 100 or less.
        This is done since the ssm api has a limit on how many accounts can
        be passed in the TargetLocations.
        Refer: https://docs.aws.amazon.com/systems-manager/latest
        /APIReference/API_StartAutomationExecution.html
        :param ssm_runbook_name: SSM Runbook name to be executed.
        :param schedule_tag_name, tag key passed as Parameters to the SSM
        Runbook
        :param schedule_tag_value, tag value passed as Parameters to the SSM
        Runbook
        :param tags, the tag key value pairs
        :param target_locations, target account and region list with assume
        role needed to run the automation in the member account with
        concurrency and error threshold
        """
        if ssm_runbook_name in [schedulers.EC2_START_SSM_DOC,
                                schedulers.EC2_STOP_SSM_DOC]:
            tag_name = "tag:" + schedule_tag_name
        else:
            tag_name = schedule_tag_name
        try:
            response = self.ssm_client.start_automation_execution(
                DocumentName=os.getenv(ssm_runbook_name),
                Parameters={
                    'TagKey': [tag_name],
                    'TagValue': [schedule_tag_value],
                    'AutomationAssumeRole': [self.automation_assume_role_arn],
                    'ResourceTagMapList': self.get_tags_in_json_formatted_string(ssm_runbook_name, tags)
                },
                TargetLocations=target_locations)
            execution_id = response["AutomationExecutionId"]
            self._logger.info(f"Automation Execution Id {execution_id}")
            return execution_id
        except Exception as exception:
            self._logger.error(f"Error while execution runbook {ssm_runbook_name} for schedule tag key {schedule_tag_name}, \
            tag value {schedule_tag_value} in region {self.regions}, accounts {self.accounts}")
            raise exception

    def run_ssm_runbook(self, ssm_runbook_name,
                        schedule_tag_name,
                        schedule_tag_value,
                        tags=[]):
        """
        Implements the API call to SSM start_automation_execution,
        :param ssm_runbook_name: SSM Runbook name to be executed.
        :param schedule_tag_name, tag key passed as Parameters to the SSM
        Runbook
        :param schedule_tag_value, tag value passed as Parameters to the SSM
        Runbook
        :param tags, the tag key value pairs
        """
        self._logger.debug(f"Initiating runbook {ssm_runbook_name}, for schedule tag key {schedule_tag_name}, \
        tag value {schedule_tag_value} in region {self.regions}, account {self.accounts}")
        max_allowed_accounts = int(self.max_allowed_accounts_in_ssm_api)
        list_of_accounts = self.accounts
        total_accounts = len(list_of_accounts)
        target_locations = []
        if total_accounts <= max_allowed_accounts:
            target_locations.append({
                'Accounts': list_of_accounts,
                'Regions': self.regions,
                'ExecutionRoleName': self.execution_role_name,
                'TargetLocationMaxConcurrency': self.max_concurrency,
                'TargetLocationMaxErrors': self.max_errors
            })
        else:
            account_index = 0
            subset_of_accounts = []
            # handle max number of account allowed in the API call
            while account_index < total_accounts:
                subset_of_accounts.append(list_of_accounts[account_index])
                account_index = account_index + 1

                if account_index % max_allowed_accounts == 0:
                    target_locations.append({
                        'Accounts': subset_of_accounts,
                        'Regions': self.regions,
                        'ExecutionRoleName': self.execution_role_name,
                        'TargetLocationMaxConcurrency': self.max_concurrency,
                        'TargetLocationMaxErrors': self.max_errors
                    })
                    subset_of_accounts = []
                elif account_index == total_accounts:
                    target_locations.append({
                        'Accounts': subset_of_accounts,
                        'Regions': self.regions,
                        'ExecutionRoleName': self.execution_role_name,
                        'TargetLocationMaxConcurrency': self.max_concurrency,
                        'TargetLocationMaxErrors': self.max_errors
                    })
                    break
        return self.execute_ssm_api(ssm_runbook_name=ssm_runbook_name,
                                    schedule_tag_name=schedule_tag_name,
                                    schedule_tag_value=schedule_tag_value,
                                    tags=tags,
                                    target_locations=target_locations)

    def run_rds_instances_document(self, schedule_tag_name,
                                   schedule_tag_value,
                                   desired_state):
        """
            Runs the rds instances documents, document is selected based on
            the desired_state.
            :param schedule_tag_name, tag key used to identify the rds instances
            :param schedule_tag_value, tag value used to identify the rds
            instances
            :param desired_state, value should be running for start
            instances, and stopped for stopping the instances.
            """
        if schedule_tag_name is None or schedule_tag_value is None or desired_state is None:
            self._logger.debug(
                f"Missing value for schedule tag key {schedule_tag_name},"
                f"tag value {schedule_tag_value}, or desired_state"
                f"{desired_state} in run_rds_instances_document")
            return None
        else:
            if desired_state == 'running':
                return self.run_ssm_runbook(schedulers.RDS_INSTANCES_START_SSM_DOC, schedule_tag_name, schedule_tag_value, self.started_tags)
            else:
                return self.run_ssm_runbook(schedulers.RDS_INSTANCES_STOP_SSM_DOC, schedule_tag_name, schedule_tag_value, self.stopped_tags)

    def run_rds_clusters_document(self, schedule_tag_name,
                                  schedule_tag_value,
                                  desired_state):
        """
            Runs the rds clusters ssm documents, ssm document is selected
            based on the desired_state.
            :param schedule_tag_name, tag key used to identify the rds instances
            :param schedule_tag_value, tag value used to identify the rds
            instances
            :param desired_state, value should be running for start
            instances, and stopped for stopping the instances.
            """
        if schedule_tag_name is None or schedule_tag_value is None or desired_state is None:
            self._logger.debug(
                f"Missing value for schedule tag key {schedule_tag_name},"
                f"tag value {schedule_tag_value}, or desired_state "
                f"{desired_state} in run_rds_clusters_document")
            return None
        else:
            if desired_state == 'running':
                return self.run_ssm_runbook(schedulers.RDS_CLUSTERS_START_SSM_DOC, schedule_tag_name, schedule_tag_value, self.started_tags)
            else:
                return self.run_ssm_runbook(schedulers.RDS_CLUSTERS_STOP_SSM_DOC, schedule_tag_name, schedule_tag_value, self.stopped_tags)

    def run_ec2_instances_document(self, schedule_tag_name,
                                   schedule_tag_value,
                                   desired_state):
        """ Runs the ec2 instances documents, document is selected based on the
        desired_state.
        :param schedule_tag_name, tag key used to identify the rds instances
        :param schedule_tag_value, tag value used to identify the rds instances
        :param desired_state, value should be running for start instances,
        and stopped for stopping the instances.
        """
        if schedule_tag_name is None or schedule_tag_value is None or \
                desired_state is None:
            self._logger.debug(
                f"Missing value for schedule tag key {schedule_tag_name},"
                f"tag value {schedule_tag_value}, or desired_state"
                f"{desired_state} in run_ec2_instances_document")
            return None
        else:
            if desired_state == 'running':
                return self.run_ssm_runbook(schedulers.EC2_START_SSM_DOC, schedule_tag_name, schedule_tag_value, self.started_tags)
            else:
                return self.run_ssm_runbook(schedulers.EC2_STOP_SSM_DOC, schedule_tag_name, schedule_tag_value, self.stopped_tags)
