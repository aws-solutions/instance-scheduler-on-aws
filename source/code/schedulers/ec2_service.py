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
import time
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
INF_ADD_KEYS = "Adding {} key(s) {} to instance(s) {}"
INFO_REMOVING_KEYS = "Removing {} key(s) {} from instance(s) {}"

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
    def get_schedulable_instances(self, kwargs):
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
    def resize_instance(self, kwargs):

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
    def get_instance_status(self, client, instance_ids):
        status_resp = client.describe_instances_with_retries(InstanceIds=instance_ids)
        jmes = "Reservations[*].Instances[*].{InstanceId:InstanceId, State:State}[]"
        return jmespath.search(jmes, status_resp)

    def get_asg(self, client, instance_ids):
        asg = client.describe_auto_scaling_instances_with_retries(InstanceIds=instance_ids)
        jmes = "AutoScalingInstances[*].AutoScalingGroupName"
        return jmespath.search(jmes, response)

    def suspend_asg(self, instance_ids):
        client = get_client_with_retries("autoscaling",
                                        ["describe_auto_scaling_instances","suspend_processes"],
                                        context=self._context, session=self._session, region=self._region)
        try:
            asg_names = self.get_asg(client, instances_ids)
            return client.suspend_processes_with_retries(
                AutoScalingGroupName=asg_names,
                ScalingProcesses=['Launch','Terminate',]
            )
        except Exception as ex:
            self._logger.error("Error suspend asg scaling {}, ({})", ",".join(instance.id), str(ex))

    def resume_asg(self, instance_ids):
        client = get_client_with_retries("autoscaling",
                                        ["describe_auto_scaling_instances","resume_processes"],
                                        context=self._context, session=self._session, region=self._region)
        try:
            asg_names = self.get_asg(client, instances_ids)
            return client.resume_processes_with_retries(
                AutoScalingGroupName=ASGName,
                ScalingProcesses=['Launch','Terminate',]
            )
        except Exception as ex:
            self._logger.error("Error resume asg scaling {}, ({})", ",".join(instance.id), str(ex))

    # noinspection PyMethodMayBeStatic
    def stop_instances(self, kwargs):

        def is_in_stopping_state(state):
            return (state & 0xFF) in Ec2Service.EC2_STOPPING_STATES

        self._init_scheduler(kwargs)

        stopped_instances = kwargs[schedulers.PARAM_STOPPED_INSTANCES]
        stop_tags = kwargs[schedulers.PARAM_CONFIG].stopped_tags
        start_tags_keys = [{"Key": t["Key"]} for t in kwargs[schedulers.PARAM_CONFIG].started_tags]

        methods = ["stop_instances", "create_tags", "delete_tags", "describe_instances"]
        client = get_client_with_retries("ec2", methods=methods, context=self._context, session=self._session, region=self._region)

        for instance_batch in self.instance_batches(stopped_instances, STOP_BATCH_SIZE):

            instance_ids = [i.id for i in list(instance_batch)]

            try:
                self.suspend_asg(instance_ids)

                stop_resp = client.stop_instances_with_retries(InstanceIds=instance_ids)
                instances_stopping = [i["InstanceId"] for i in stop_resp.get("StoppingInstances", []) if
                                      is_in_stopping_state(i.get("CurrentState", {}).get("Code", ""))]

                get_status_count = 0
                if len(instances_stopping) < len(instance_ids):
                    time.sleep(5)

                    instances_stopping = [i["InstanceId"] for i in self.get_instance_status(client, instance_ids) if
                                          is_in_stopping_state(i.get("State", {}).get("Code", ""))]

                    if len(instances_stopping) == len(instance_ids):
                        break

                    get_status_count += 1
                    if get_status_count > 3:
                        for i in instance_ids:
                            if i not in instances_stopping:
                                self._logger.warning(WARNING_INSTANCE_NOT_STOPPING, i)
                        break

                if len(instances_stopping) > 0:
                    try:
                        if start_tags_keys is not None and len(start_tags_keys):
                            self._logger.info(INFO_REMOVING_KEYS, "start",
                                              ",".join(["\"{}\"".format(k["Key"]) for k in start_tags_keys]),
                                              ",".join(instances_stopping))
                            client.delete_tags_with_retries(Resources=instances_stopping, Tags=start_tags_keys)
                        if stop_tags is not None and len(stop_tags) > 0:
                            self._logger.info(INF_ADD_KEYS, "stop", str(stop_tags), ",".join(instances_stopping))
                            client.create_tags_with_retries(Resources=instances_stopping, Tags=stop_tags)
                    except Exception as ex:
                        self._logger.warning(WARN_STOPPED_INSTANCES_TAGGING, ','.join(instances_stopping), str(ex))

                for i in instances_stopping:
                    yield i, InstanceSchedule.STATE_STOPPED

            except Exception as ex:
                self._logger.error(ERR_STOPPING_INSTANCES, ",".join(instance_ids), str(ex))

    # noinspection PyMethodMayBeStatic
    def start_instances(self, kwargs):

        def is_in_starting_state(state):
            return (state & 0xFF) in Ec2Service.EC2_STARTING_STATES

        self._init_scheduler(kwargs)

        instances_to_start = kwargs[schedulers.PARAM_STARTED_INSTANCES]
        start_tags = kwargs[schedulers.PARAM_CONFIG].started_tags
        stop_tags_keys = [{"Key": t["Key"]} for t in kwargs[schedulers.PARAM_CONFIG].stopped_tags]
        client = get_client_with_retries("ec2", ["start_instances", "describe_instances", "create_tags", "delete_tags"],
                                         context=self._context, session=self._session, region=self._region)

        for instance_batch in self.instance_batches(instances_to_start, START_BATCH_SIZE):

            instance_ids = [i.id for i in list(instance_batch)]
            try:
                start_resp = client.start_instances_with_retries(InstanceIds=instance_ids)
                instances_starting = [i["InstanceId"] for i in start_resp.get("StartingInstances", []) if
                                      is_in_starting_state(i.get("CurrentState", {}).get("Code", ""))]

                get_status_count = 0
                if len(instances_starting) < len(instance_ids):
                    time.sleep(5)

                    instances_starting = [i["InstanceId"] for i in self.get_instance_status(client, instance_ids) if
                                          is_in_starting_state(i.get("State", {}).get("Code", ""))]

                    if len(instances_starting) == len(instance_ids):
                        break

                    get_status_count += 1
                    if get_status_count > 3:
                        for i in instance_ids:
                            if i not in instances_starting:
                                self._logger.warning(WARNING_INSTANCE_NOT_STARTING, i)
                        break

                if len(instances_starting) > 0:
                    try:
                        if stop_tags_keys is not None and len(stop_tags_keys) > 0:
                            self._logger.info(INFO_REMOVING_KEYS, "stop",
                                              ",".join(["\"{}\"".format(k["Key"]) for k in stop_tags_keys]),
                                              ",".join(instances_starting))
                            client.delete_tags_with_retries(Resources=instances_starting, Tags=stop_tags_keys)
                        if start_tags is not None and len(start_tags) > 0:
                            self._logger.info(INF_ADD_KEYS, "start", str(start_tags), ",".join(instances_starting))
                            client.create_tags_with_retries(Resources=instances_starting, Tags=start_tags)
                    except Exception as ex:
                        self._logger.warning(WARN_STARTED_INSTANCES_TAGGING, ','.join(instances_starting), str(ex))

                for i in instances_starting:
                    yield i, InstanceSchedule.STATE_RUNNING

                self.resume_asg(instance_ids)

            except Exception as ex:
                self._logger.error(ERR_STARTING_INSTANCES, ",".join(instance_ids), str(ex))
