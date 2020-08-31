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
from schedulers.ec2_service import Ec2Service
from schedulers.rds_service import RdsService

INST_ALLOW_RESIZE = "allow_resize"
INST_RESIZED = "resized"
INST_ARN = "arn"
INST_CURRENT_STATE = "current_state"
INST_ID = "id"
INST_INSTANCE_TYPE = "instancetype"
INST_IS_RUNNING = "is_running"
INST_IS_TERMINATED = "is_terminated"
INST_MULTI_AZ = "multi_az"
INST_NAME = "name"
INST_SCHEDULE = "schedule_name"
INST_HIBERNATE = "hibernate"
INST_STATE = "state"
INST_STATE_NAME = "state_name"
INST_TAGS = "tags"
INST_MAINTENANCE_WINDOW = "maintenance_window"
INST_ENGINE_TYPE = "engine_type"
INST_DB_ARN = "db_inst_arn"
INST_DB_IS_CLUSTER = "is_cluster"

PARAM_ACCOUNT = "account"
PARAM_CONTEXT = "context"
PARAM_DESIRED_TYPE = "desired_type"
PARAM_INSTANCE = "instance"
PARAM_LOGGER = "logger"
PARAM_REGION = "region"
PARAM_ROLE = "role"
PARAM_SESSION = "session"
PARAM_STARTED_INSTANCES = "started_instances"
PARAM_STOPPED_INSTANCES = "stopped_instances"
PARAM_TAG_NAME = "tagname"
PARAM_TRACE = "trace"
PARAM_STACK = "stack_name"
PARAM_CONFIG = "configuration"
PARAM_CLUSTERS = "clusters"


# Services handled by the scheduler, the class that handles the logic for scheduling instances for each know service
# must be registered here

SCHEDULER_TYPES = {
    "ec2": Ec2Service,
    "rds": RdsService
}


def account_from_role(role_str):
    role_elements = role_str.split(":")
    if len(role_elements) < 5:
        return ""
    return role_elements[4]

