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

class CloudFormationUtil:
    def __init__(self, stack_name, credentials = None):
        self.stack_name = stack_name
        if credentials == None:
            self.cfn_resource = boto3.resource("cloudformation")
        else:
            self.cfn_resource = boto3.resource(
                "cloudformation",
                aws_access_key_id=credentials['AccessKeyId'],
                aws_secret_access_key=credentials['SecretAccessKey'],
                aws_session_token=credentials['SessionToken']
            )

    @lru_cache(maxsize=1)
    def get_physical_resource_id(self, logical_id):
        try:
            physical_resource_id = self.cfn_resource.StackResource(self.stack_name, logical_id).physical_resource_id
            return physical_resource_id
        except Exception as e:
            print('Failed to get resouce [{logical_id}] details. Exception: {}'.format(e))
            return None

    def get_config_table_id(self):
        return self.get_physical_resource_id('ConfigTable')

    def get_lambda_function_id(self):
        return self.get_physical_resource_id('Main')

    def get_stack_status(self):
        try:
            stack_status = self.cfn_resource.Stack(self.stack_name).stack_status
            print(f'stack [{self.stack_name}] status: {stack_status}')
            return stack_status
        except Exception as e:
            print(f'Returning ERROR. Exception: {e}')
            return "ERROR"

    def get_stack_output(self, output_key):
        try:
            stack_outputs = self.cfn_resource.Stack(self.stack_name).outputs
            for output in stack_outputs:
                if output['OutputKey'] == output_key:
                    stack_output = output['OutputValue']
                    print(f'stack [{self.stack_name}] output for key [{output_key}]: {stack_output}')
                    return stack_output

            return None
        except Exception as e:
            print(f'Returning ERROR. Exception: {e}')
            return None

    def is_stack_in_complete_state(self, stack_state):
        complete_states = ['CREATE_COMPLETE', 'UPDATE_COMPLETE']
        return stack_state in complete_states

    def is_stack_in_progress_state(self, stack_state):
        progress_states = ['CREATE_IN_PROGRESS', 'UPDATE_IN_PROGRESS', 'UPDATE_COMPLETE_CLEANUP_IN_PROGRESS']
        return stack_state in progress_states

    def is_stack_exists(self):
        print(f'checking if {self.stack_name} exists.')
        stack_status = self.get_stack_status()
        if self.is_stack_in_complete_state(stack_status):
            return True

        print(f'stack named {self.stack_name} is not in invalid state [{stack_status}]')
        return False

    def update_stack_params(self, params_to_update):
        all_param_keys = [
            'ScheduledServices',
            'CreateRdsSnapshot',
            'CrossAccountRoles',
            'Regions',
            'StartedTags',
            'StoppedTags',
            'SchedulerFrequency',
            'SchedulingActive',
            'Trace'
        ]

        update_params = []

        for key in all_param_keys:
            if key in params_to_update:
                update_params.append(
                    { 'ParameterKey': key, 'ParameterValue': params_to_update[key] }
                )
            else:
                update_params.append(
                    { 'ParameterKey': key, 'UsePreviousValue': True }
                )

        return update_params

    def enable_rds_snapshot_param(self, params):
        params.update(CreateRdsSnapshot = 'Yes')

    def disable_rds_snapshot_param(self, params):
        params.update(CreateRdsSnapshot = 'No')

    def set_cross_account_role_param(self, params, cross_account_role_arn):
        if cross_account_role_arn == None:
            print('Invalid cross account role arn to set')
            return

        params.update(CrossAccountRoles = cross_account_role_arn)

    def unset_cross_account_role_param(self, params):
        params.update(CrossAccountRoles = '')

    def set_scheduled_services_to_rds_param(self, params):
        params.update(ScheduledServices = 'RDS')

    def set_scheduled_services_to_ec2_param(self, params):
        params.update(ScheduledServices = 'EC2')

    def update_stack(self, params):
        try:
            self.cfn_resource.Stack(self.stack_name).update(
                UsePreviousTemplate=True,
                Parameters=params,
                Capabilities=['CAPABILITY_IAM']
            )
        except Exception as e:
            print(f'Unable to update stack. Exception: {e}')
            return

        # wait for stack to update
        while True:
            stack_status = self.get_stack_status()

            if self.is_stack_in_progress_state(stack_status):
                print('waiting for 5 seconds...')
                time.sleep(5)
            elif self.is_stack_in_complete_state(stack_status):
                print(f'Update completed. stack {self.stack_name} is in [{stack_status}] state')
                break
