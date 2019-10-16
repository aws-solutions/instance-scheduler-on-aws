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

class Ec2Util:
    def __init__(self, ec2_instance_identifier, credentials = None):
        self.ec2_instance_identifier = ec2_instance_identifier

        if credentials == None:
            self.ec2_client = boto3.client("ec2")
        else:
            self.ec2_client = boto3.client(
                "ec2",
                aws_access_key_id=credentials['AccessKeyId'],
                aws_secret_access_key=credentials['SecretAccessKey'],
                aws_session_token=credentials['SessionToken']
            )

    def _get_ec2_instance_by_id(self, instance_id):
        if not instance_id or instance_id.isspace():
            print(f'Invalid value to param [instance_id].')
            return "ERROR"

        try:
            ec2_instance = self.ec2_client.describe_instances(InstanceIds=[instance_id])
            return ec2_instance
        except Exception as e:
            print(f'Failed to get instance [{instance_id}] details. Exception: {e}')
            return "ERROR"

    def _get_ec2_instance_by_tag(self, tag_name, tag_val):
        try:
            filter = [
                {
                    'Name': f'tag:{tag_name}',
                    'Values': [ tag_val ]
                }
            ]

            ec2_instance = self.ec2_client.describe_instances(Filters=filter)
            return ec2_instance
        except Exception as e:
            print(f'Failed to get instance details with tag [{tag_name} : {tag_val}]. Exception: {e}')
            return "ERROR"

    def get_ec2_status(self):
        try:
            ec2_instance = self._get_ec2_instance_by_id(self.ec2_instance_identifier)
            ec2_current_status = ec2_instance['Reservations'][0]['Instances'][0]['State']['Name']
            print(f'EC2 [{self.ec2_instance_identifier}] current status: {ec2_current_status}')
            return ec2_current_status
        except Exception as e:
            print(f'Returning ERROR. Exception: {e}')
            return "ERROR"

    def validate_ec2_expected_state(self, expected_state):
        intervals = 0
        while True:
            ec2_status = self.get_ec2_status()
            if ec2_status == expected_state:
                return True
            
            print(f'EC2 [{self.ec2_instance_identifier}] expected status: {expected_state}')
            print(f'Wait for 5 seconds. Elaspsed time: {intervals * 5} seconds')
            intervals += 1
            if intervals > 120 and ec2_status in ['stopped', 'available']:
                print(f'Initial state of EC2 [{self.ec2_instance_identifier}] was not changed in last 10 minutes. Waited too long. Existing...')
                return False

            time.sleep(5)
