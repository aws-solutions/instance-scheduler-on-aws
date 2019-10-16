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

from cloudformation_util import *
from dynamodb_util import *
from ec2_util import *
from lambda_util import *
from sts_util import *
import os

# ASSUMPTION: you have CFN stack locally and remotely.
local_stack = "is-122"
remote_stack = "is-122-remote"

# ASSUMPTION: you have EC2 instance locally and remotely.
local_ec2_instance_identifier = "i-0e4c5b83a4b9ccae9"
remote_ec2_instance_identifier = "i-0856a89699fcd7ec2"

# ASSUMPTION: you have a cross account role to access remote account's resources from local account.
iam_role_name = "InstanceScheduler"
aws_account_id = "<AWS_ACCOUNT_ID>" # AWS account Id where the iam_role is created
remote_account_assume_role_arn = f"arn:aws:iam::{aws_account_id}:role/{iam_role_name}"

def setup_and_execute_scheduler(with_remote_ec2):
    start_time = time.time()

    # collection of parameters for updating stack
    params_to_update = {}

    if with_remote_ec2:
        cross_account_role_arn = cfn_remote.get_stack_output('CrossAccountRole')
        cfn_local.set_cross_account_role_param(params_to_update, cross_account_role_arn)
        ec2_obj = ec2_remote
    else:
        cfn_local.unset_cross_account_role_param(params_to_update)
        ec2_obj = ec2_local

    params = cfn_local.update_stack_params(params_to_update)
    cfn_local.update_stack(params)

    ec2_current_status = ec2_obj.get_ec2_status()
    ec2_expected_state = 'stopped' if ec2_current_status == 'running' else 'running'

    # set timer in config table for 'test-period'
    update_period_config(config_table)
    exec_scheduler()

    if ec2_obj.validate_ec2_expected_state(ec2_expected_state):
        print('SUCCESSFULL')
    else:
        print('FAILED')

    elapsed_time = time.time() - start_time
    print(f'Test Ended. Elapsed time: {elapsed_time}')

def schedule_for_local_ec2_instance():
    print('=== Starting Test: LOCAL EC2 ===')
    setup_and_execute_scheduler(False)

def schedule_for_remote_ec2_instance():
    print('=== Starting Test: REMOTE EC2 ===')
    setup_and_execute_scheduler(True)

def exec_scheduler():
    try:
        lambda_function_id = cfn_local.get_lambda_function_id()
        env_variables = get_lambda_env_variables(lambda_function_id)

        for env_var in env_variables:
            os.environ[env_var] = env_variables[env_var]

    except Exception as e:
        print(f'Error setting up environment, {e}')
        return

    scheduler_rule = os.getenv("SCHEDULER_RULE")
    event = {
        "source": "aws.events",
        "detail-type": "Scheduled Event",
        "resources": [f'arn/{scheduler_rule}']
    }

    invoke_lambda_function(lambda_function_id, event)

if __name__ == "__main__":
    cross_account_credentials = get_assume_role_credentials(remote_account_assume_role_arn)

    cfn_local = CloudFormationUtil(local_stack)
    cfn_remote = CloudFormationUtil(remote_stack, cross_account_credentials)

    ec2_local = Ec2Util(local_ec2_instance_identifier)
    ec2_remote = Ec2Util(remote_ec2_instance_identifier, cross_account_credentials)

    if not cfn_local.is_stack_exists():
        print(f'Make sure your local stack {local_stack} is in valid state')
    elif not cfn_remote.is_stack_exists():
        print(f'Make sure your remote stack {remote_stack} is in valid state')
    else:
        # pre-cofigure config setting
        config_table_id = cfn_local.get_config_table_id()
        config_table = get_config_table(config_table_id)

        # Check if 'test-schedule' item exists in 'schedule' table. If not, put an item.
        setup_schedule_config(config_table)

        # Check if 'test-period' item exists in 'period' table. If not, put an item.
        setup_period_config(config_table)

        # Since tests are inteded for EC2, setting scheduled service to RDS only
        params_to_update = {}
        cfn_local.set_scheduled_services_to_ec2_param(params_to_update)
        params = cfn_local.update_stack_params(params_to_update)
        cfn_local.update_stack(params)

        #schedule_for_local_ec2_instance()
        schedule_for_remote_ec2_instance()
