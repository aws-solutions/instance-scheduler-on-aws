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

class RdsUtil:
    def __init__(self, rds_instance_identifier, snapshot_identifier, credentials = None):
        self.rds_instance_identifier = rds_instance_identifier
        self.snapshot_identifier = snapshot_identifier
        if credentials == None:
            self.rds_client = boto3.client("rds")
        else:
            self.rds_client = boto3.client(
                "rds",
                aws_access_key_id=credentials['AccessKeyId'],
                aws_secret_access_key=credentials['SecretAccessKey'],
                aws_session_token=credentials['SessionToken']
            )

    def get_rds_status(self):
        try:
            rds_instances = self.rds_client.describe_db_instances(DBInstanceIdentifier=self.rds_instance_identifier)
            rds_current_status = rds_instances['DBInstances'][0]['DBInstanceStatus']
            print(f'RDS [{self.rds_instance_identifier}] current status: {rds_current_status}')
            return rds_current_status
        except Exception as e:
            print(f'Returning ERROR. Exception: {e}')
            return "ERROR"

    def validate_rds_expected_state(self, expected_state):
        intervals = 0
        while True:
            rds_status = self.get_rds_status()
            if rds_status == expected_state:
                return True
            
            # Shutting down RDS takes longer if "CreateRdsSnapshot" flag is enabled. 
            print(f'RDS [{self.rds_instance_identifier}] expected status: {expected_state}')
            print(f'Wait for 5 seconds. Elaspsed time: {intervals * 5} seconds')
            intervals += 1
            if intervals > 120 and rds_status in ['stopped', 'available']:
                print(f'Initial state of RDS [{self.rds_instance_identifier}] was not changed in last 10 minutes. Waited too long. Existing...')
                return False

            time.sleep(5)

    def get_rds_snapshot_create_time(self):
        try:
            rds_snapshot = self.rds_client.describe_db_snapshots(DBSnapshotIdentifier=self.snapshot_identifier)
            rds_snapshot_create_time = rds_snapshot['DBSnapshots'][0]['SnapshotCreateTime']
            print(f'RDS snapshot [{self.snapshot_identifier}] current create time: {rds_snapshot_create_time}')
            return rds_snapshot_create_time
        except Exception as e:
            print(f'Failed to retrieve RDS snapshot [{self.snapshot_identifier}] create time. Exception: {e}')
            return None

    def validate_rds_snapshot_create_time(self, rds_snapshot_previous_create_time, rds_instance_status):
        if rds_instance_status == "available":
            # snapshot is not created when RDS turned on
            return True

        rds_snapshot_current_create_time = self.get_rds_snapshot_create_time()
        return (rds_snapshot_previous_create_time == None and rds_snapshot_current_create_time != None) or (rds_snapshot_current_create_time > rds_snapshot_previous_create_time)
