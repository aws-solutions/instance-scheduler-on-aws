######################################################################################################################
#  Copyright 2016 Amazon.com, Inc. or its affiliates. All Rights Reserved.                                           #
#                                                                                                                    #
#  Licensed under the Amazon Software License (the "License"). You may not use this file except in compliance        #
#  with the License. A copy of the License is located at                                                             #
#                                                                                                                    #
#      http://aws.amazon.com/asl/                                                                                    #
#                                                                                                                    #
#  or in the "license" file accompanying this file. This file is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES #
#  OR CONDITIONS OF ANY KIND, express or implied. See the License for the specific language governing permissions    #
#  and limitations under the License.                                                                                #
######################################################################################################################

import jmespath

import schedulers
from boto_retry import get_client_with_retries
from configuration.instance_schedule import InstanceSchedule

# instances are started in batches, larger bathes are more efficient but smaller batches allow more instances
# to start if we run into resource limits
START_BATCH_SIZE = 5
STOP_BATCH_SIZE = 50

ERR_STARTING_INSTANCES = "Error starting instances {}, ({})"
ERR_STOPPING_INSTANCES = "Error stopping instances {}, ({})"

INF_FETCHED_INSTANCES = "Number of fetched ec2 instances is {}, number of instances in a schedulable state is {}"
INF_FETCHING_INSTANCES = "Fetching ec2 instances for account {} in region {}"
INF_SETTING_SIZE = "Setting size for ec2 instance {} to {}"

WARN_STARTED_INSTANCES_TAGGING = "Error deleting or creating tags for started instances {} ({})"
WARN_STOPPED_INSTANCES_TAGGING = "Error deleting or creating tags for stopped instances {} ({})"
WARNING_INSTANCE_NOT_STARTING = "Ec2 instance {} is not started"
WARNING_INSTANCE_NOT_STOPPING = "Ec2 instance {} is not stopped"

DEBUG_SKIPPED_INSTANCE = "Skipping ec2 instance {} because it it not in a schedulable state ({})"
DEBUG_SELECTED_INSTANCE = "Selected ec2 instance {} in state ({})"


class Ec2Service:
    """
    Implements service start/stop/resize functions for ECS service
    """
    EC2_STATE_PENDING = 0
    EC2_STATE_RUNNING = 16
    EC2_STATE_SHUTTING_DOWN = 32
    EC2_STATE_TERMINATED = 48
    EC2_STATE_STOPPING = 64
    EC2_STATE_STOPPED = 80

    EC2_SCHEDUABLE_STATES = {EC2_STATE_RUNNING, EC2_STATE_STOPPED}
    EC2_STOPPING_STATES = {EC2_STATE_SHUTTING_DOWN, EC2_STATE_STOPPING, EC2_STATE_STOPPED}
    EC2_STARTING_STATES = {EC2_STATE_PENDING, EC2_STATE_RUNNING}

    def __init__(self):
        self.service_name = "ec2"
        self.allow_resize = True

    def _init_scheduler(self, args):
        self._session = args.get(schedulers.PARAM_SESSION)
        self._context = args.get(schedulers.PARAM_CONTEXT)
        self._region = args.get(schedulers.PARAM_REGION)
        self._logger = args.get(schedulers.PARAM_LOGGER)
        self._account = args.get(schedulers.PARAM_ACCOUNT)
        self._tagname = args.get(schedulers.PARAM_TAG_NAME)

    @classmethod
    def instance_batches(cls, instances, size):
        instance_buffer = []
        for instance in instances:
            instance_buffer.append(instance)
            if len(instance_buffer) == size:
                yield instance_buffer
                instance_buffer = []
        if len(instance_buffer) > 0:
            yield instance_buffer

    # get instances and handle paging
    def get_schedulable_instances(self, **kwargs):
        session = kwargs[schedulers.PARAM_SESSION]
        context = kwargs[schedulers.PARAM_CONTEXT]
        region = kwargs[schedulers.PARAM_REGION]
        account = kwargs[schedulers.PARAM_ACCOUNT]
        logger = kwargs[schedulers.PARAM_LOGGER]
        tagname = kwargs[schedulers.PARAM_TAG_NAME]

        client = get_client_with_retries("ec2", ["describe_instances"], context=context, session=session, region=region)

        def is_in_schedulable_state(ec2_inst):
            state = ec2_inst["state"] & 0xFF
            return state in Ec2Service.EC2_SCHEDUABLE_STATES

        jmes = "Reservations[*].Instances[*].{InstanceId:InstanceId, EbsOptimized:EbsOptimized, Tags:Tags, " \
               "InstanceType:InstanceType,State:State}[]" + \
               "|[?Tags]|[?contains(Tags[*].Key, '{}')]".format(tagname)

        args = {}
        number_of_instances = 0
        instances = []
        done = False

        logger.info(INF_FETCHING_INSTANCES, account, region)

        while not done:

            ec2_resp = client.describe_instances_with_retries(**args)
            for reservation_inst in jmespath.search(jmes, ec2_resp):
                inst = self._select_instance_data(instance=reservation_inst, tagname=tagname)
                number_of_instances += 1
                if is_in_schedulable_state(inst):
                    instances.append(inst)
                    logger.debug(DEBUG_SELECTED_INSTANCE, inst[schedulers.INST_ID], inst[schedulers.INST_STATE_NAME])
                else:
                    logger.debug(DEBUG_SKIPPED_INSTANCE, inst[schedulers.INST_ID], inst[schedulers.INST_STATE_NAME])
            if "NextToken" in ec2_resp:
                args["NextToken"] = ec2_resp["NextToken"]
            else:
                done = True
        logger.info(INF_FETCHED_INSTANCES, number_of_instances, len(instances))
        return instances

    # selects and builds a named tuple for the instance data
    def _select_instance_data(self, instance, tagname):

        def get_tags(inst):
            return {tag["Key"]: tag["Value"] for tag in inst["Tags"]} if "Tags" in inst else {}

        tags = get_tags(instance)
        name = tags.get("Name", "")
        instance_id = instance["InstanceId"]
        state = instance["State"]["Code"] & 0XFF
        is_running = self.EC2_STATE_RUNNING == state
        is_terminated = state == Ec2Service.EC2_STATE_TERMINATED
        instance_data = {
            schedulers.INST_ID: instance_id,
            schedulers.INST_SCHEDULE: tags.get(tagname),
            schedulers.INST_NAME: name,
            schedulers.INST_STATE: state,
            schedulers.INST_STATE_NAME: instance["State"]["Name"],
            schedulers.INST_ALLOW_RESIZE: self.allow_resize,
            schedulers.INST_IS_RUNNING: is_running,
            schedulers.INST_IS_TERMINATED: is_terminated,
            schedulers.INST_CURRENT_STATE: InstanceSchedule.STATE_RUNNING if is_running else InstanceSchedule.STATE_STOPPED,
            schedulers.INST_INSTANCE_TYPE: instance["InstanceType"],
            schedulers.INST_TAGS: tags,
            schedulers.INST_MAINTENANCE_WINDOW: None
        }
        return instance_data

    # noinspection PyMethodMayBeStatic
    def resize_instance(self, **kwargs):

        self._init_scheduler(kwargs)
        instance = kwargs[schedulers.PARAM_INSTANCE]
        instance_type = kwargs[schedulers.PARAM_DESIRED_TYPE]

        client = get_client_with_retries("ec2", ["modify_instance_attribute"],
                                         context=self._context, session=self._session, region=self._region)

        self._logger.info(INF_SETTING_SIZE, instance.id, instance_type)

        try:
            client.modify_instance_attribute_with_retries(InstanceId=instance.id, InstanceType={"Value": instance_type})
        except Exception as ex:
            self._logger.error("Error resizing instance {}, ({})", ",".join(instance.id), str(ex))

    # noinspection PyMethodMayBeStatic
    def stop_instances(self, **kwargs):

        def is_in_stopping_state(state):
            return (state & 0xFF) in Ec2Service.EC2_STOPPING_STATES

        self._init_scheduler(kwargs)

        stopped_instances = kwargs[schedulers.PARAM_STOPPED_INSTANCES]
        stop_tags = kwargs[schedulers.PARAM_CONFIG].stopped_tags
        start_tags_keys = [{"Key": t["Key"]} for t in kwargs[schedulers.PARAM_CONFIG].started_tags]

        methods = ["stop_instances", "create_tags", "delete_tags"]
        client = get_client_with_retries("ec2", methods=methods, context=self._context, session=self._session, region=self._region)

        for instance_batch in self.instance_batches(stopped_instances, STOP_BATCH_SIZE):

            instances_stopping = []
            instance_ids = [i.id for i in list(instance_batch)]

            try:
                stop_resp = client.stop_instances_with_retries(InstanceIds=instance_ids)
                for stopped_instance in stop_resp["StoppingInstances"]:
                    if is_in_stopping_state(stopped_instance["CurrentState"]["Code"]):
                        instances_stopping.append(stopped_instance["InstanceId"])
                        yield stopped_instance["InstanceId"], InstanceSchedule.STATE_STOPPED
                    else:
                        self._logger.warning(WARNING_INSTANCE_NOT_STOPPING, stopped_instance["InstanceId"])
            except Exception as ex:
                self._logger.error(ERR_STOPPING_INSTANCES, ",".join(instance_ids), str(ex))

            if len(instances_stopping) > 0:
                try:
                    if start_tags_keys is not None and len(start_tags_keys):
                        client.delete_tags_with_retries(Resources=instances_stopping, Tags=start_tags_keys)
                    if stop_tags is not None and len(stop_tags) > 0:
                        client.create_tags_with_retries(Resources=instances_stopping, Tags=stop_tags)
                except Exception as ex:
                    self._logger.warning(WARN_STOPPED_INSTANCES_TAGGING, ','.join(instances_stopping), str(ex))

    # noinspection PyMethodMayBeStatic
    def start_instances(self, **kwargs):

        def is_in_starting_state(state):
            return (state & 0xFF) in Ec2Service.EC2_STARTING_STATES

        self._init_scheduler(kwargs)

        started_instances = kwargs[schedulers.PARAM_STARTED_INSTANCES]
        start_tags = kwargs[schedulers.PARAM_CONFIG].started_tags
        stop_tags_keys = [{"Key": t["Key"]} for t in kwargs[schedulers.PARAM_CONFIG].stopped_tags]
        client = get_client_with_retries("ec2", ["start_instances", "create_tags", "delete_tags"],
                                         context=self._context, session=self._session, region=self._region)

        for instance_batch in self.instance_batches(started_instances, START_BATCH_SIZE):

            instances_starting = []

            instance_ids = [i.id for i in list(instance_batch)]
            try:
                start_resp = client.start_instances_with_retries(InstanceIds=instance_ids)

                for started_instance in start_resp["StartingInstances"]:
                    if is_in_starting_state(started_instance["CurrentState"]["Code"]):
                        instances_starting.append(started_instance["InstanceId"])
                        yield started_instance["InstanceId"], InstanceSchedule.STATE_RUNNING
                    else:
                        self._logger.warning(WARNING_INSTANCE_NOT_STARTING, started_instance["InstanceId"])
            except Exception as ex:
                self._logger.error(ERR_STARTING_INSTANCES, ",".join(instance_ids), str(ex))

            if len(instances_starting) > 0:
                try:
                    if stop_tags_keys is not None and len(stop_tags_keys):
                        client.delete_tags_with_retries(Resources=instances_starting, Tags=stop_tags_keys)
                    if start_tags is not None and len(start_tags) > 0:
                        client.create_tags_with_retries(Resources=instances_starting, Tags=start_tags)
                except Exception as ex:
                    self._logger.warning(WARN_STARTED_INSTANCES_TAGGING, ','.join(instances_starting), str(ex))
