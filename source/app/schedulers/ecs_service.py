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

import copy
import re

import schedulers
import re
import copy
import jmespath

from boto_retry import get_client_with_standard_retry
from configuration.instance_schedule import InstanceSchedule
from configuration.running_period import RunningPeriod
from configuration.scheduler_config_builder import SchedulerConfigBuilder
from configuration.setbuilders.weekday_setbuilder import WeekdaySetBuilder

RESTRICTED_RDS_TAG_VALUE_SET_CHARACTERS = r"[^a-zA-Z0-9\s_\.:+/=\\@-]"

WARN_RDS_TAG_VALUE = "Tag value \"{}\" for tag \"{}\" changed to \"{}\" because it did contain characters that are not allowed " \
    "in RDS tag values. The value can only contain only the set of Unicode letters, digits, " \
                     "white-space, '_', '.', '/', '=', '+', '-'"


class EcsService:
    ECS_STATE_ACTIVE = "ACTIVE"
    ECS_STATE_INACTIVE = "INACTIVE"
    ECS_SCHEDULABLE_STATES = {ECS_STATE_ACTIVE, ECS_STATE_INACTIVE}
    DESIRED_COUNT_TAG_NAME = "instance-scheduler:desired-count"

    def __init__(self):
        self.service_name = "ecs"
        self.allow_resize = False

        self._context = None
        self._session = None
        self._region = None
        self._account = None
        self._logger = None
        self._tagname = None
        self._stack_name = None
        self._config = None

    def _init_scheduler(self, args):
        """
        Initializes common parameters
        :param args: action parameters
        :return:
        """
        self._context = args.get(schedulers.PARAM_CONTEXT)
        self._session = args.get(schedulers.PARAM_SESSION)
        self._region = args.get(schedulers.PARAM_REGION)
        self._account = args.get(schedulers.PARAM_ACCOUNT)
        self._logger = args.get(schedulers.PARAM_LOGGER)
        self._tagname = args.get(schedulers.PARAM_CONFIG).tag_name
        self._stack_name = args.get(schedulers.PARAM_STACK)
        self._config = args.get(schedulers.PARAM_CONFIG)

    def _get_client(self):
        return get_client_with_standard_retry("ecs",
                                              session=self._session,
                                              region=self._region)

    def get_schedulable_instances(self, kwargs):
        """Returns the ECS Service that can be scheduled

        Args:
            kwargs (_type_): _description_

        Returns:
            list: a list of ECS Services that can be scheduled
        """
        self._session = kwargs[schedulers.PARAM_SESSION]
        region = kwargs[schedulers.PARAM_REGION]
        account = kwargs[schedulers.PARAM_ACCOUNT]
        tagname = kwargs[schedulers.PARAM_CONFIG].tag_name
        config = kwargs[schedulers.PARAM_CONFIG]

        self._init_scheduler(kwargs)
        client = self._get_client()

        jmes = "services[*].{clusterArn:clusterArn, serviceArn:serviceArn, serviceName:serviceName, status:status, desiredCount:desiredCount, tags:tags}[]" + \
               "|[?tags]|[?contains(tags[*].key, '{}')]".format(tagname)

        number_of_ecs_services = 0
        schedulable_ecs_services = []
        self._logger.info("Fetching ECS Services for account {} in region {}",
                          account,
                          region)

        all_ecs_services = self._get_all_ecs_services(client)
        for cluster_arn, cluster_services in all_ecs_services.items():
            # At most 10 ECS Service at once...
            number_of_ecs_services += len(cluster_services)
            for chunk in [cluster_services[i:i+10] for i in range(0, len(cluster_services), 10)]:
                response = client.describe_services(cluster=cluster_arn,
                                                    services=chunk,
                                                    include=['TAGS'])
                # jmespath.search(jmes, response):
                for ecs_service_raw in response['services']:
                    ecs_service = self._select_resource_data(ecs_service_raw)
                    if self._is_schedulable(ecs_service):
                        schedulable_ecs_services.append(ecs_service)
                        self._logger.debug("Selected ECS Service {} in state ({}) for schedule {}",
                                           ecs_service[schedulers.INST_NAME],
                                           ecs_service[schedulers.INST_STATE_NAME],
                                           ecs_service[schedulers.INST_SCHEDULE])
        self._logger.info(
            "Number of fetched ECS Services is {}, number of ECS Services in a schedulable state is {}",
            number_of_ecs_services,
            len(schedulable_ecs_services))
        return schedulable_ecs_services

    def _get_all_ecs_services(self, client):
        """Returns a dict of ECS Services grouped by Cluster ARN

        Args:
            client: The ECS Client

        Returns:
            dict: a a map of ECS Cluster ARN -> array of ECS Service ARNs
        """
        services = {}
        for p_cluster in client.get_paginator("list_clusters").paginate():
            for cluster_arn in p_cluster['clusterArns']:
                services[cluster_arn] = []
                for p_service in client.get_paginator("list_services").paginate(cluster=cluster_arn):
                    for service_arn in p_service['serviceArns']:
                        services[cluster_arn].append(service_arn)
        return services

    def _is_schedulable(self, ecs_service):
        service_name = ecs_service[schedulers.INST_NAME]
        status = ecs_service[schedulers.INST_STATE]
        schedule = ecs_service[schedulers.INST_SCHEDULE]
        desired_count = ecs_service[schedulers.INST_ECS_DESIRED_COUNT]
        running_count = ecs_service[schedulers.INST_ECS_RUNNING_COUNT]
        if status not in EcsService.ECS_SCHEDULABLE_STATES:
            self._logger.debug("Skipping ECS Service {} because it is not in a start or stop-able state ({})",
                               service_name,
                               status)
            return False
        if not schedule:
            self._logger.debug("Skipping ECS Service {} because it has no schedule tag named {}",
                               service_name,
                               self._tagname)
            return False
        # XXX: Need to compare desiredCount and runningCount as if they are different,
        # it means that some deployment is ongoing.
        if desired_count != running_count:
            self._logger.debug("Skipping ECS Service {} because it a deployment is pending: only {}/{} tasks are ready",
                               service_name,
                               running_count,
                               desired_count)
            return False
        return True

    def _select_resource_data(self, ecs_service):

        status = ecs_service["status"]
        desired_count = ecs_service["desiredCount"]
        running_count = ecs_service["runningCount"]
        is_running = status == self.ECS_STATE_ACTIVE and desired_count > 0
        tags = ecs_service["tags"]
        schedule = {tag["key"]: tag["value"] for tag in tags if tag["key"] in [
            self._tagname]}.get(self._tagname, None)
        org_desired_count = {tag["key"]: tag["value"] for tag in tags if tag["key"] in [
            self.DESIRED_COUNT_TAG_NAME]}.get(self.DESIRED_COUNT_TAG_NAME, desired_count)

        instance_data = {
            schedulers.INST_ID: ecs_service["serviceArn"],
            schedulers.INST_ECS_CLUSTER_ARN: ecs_service["clusterArn"],
            schedulers.INST_ECS_DESIRED_COUNT: desired_count,
            schedulers.INST_ECS_RUNNING_COUNT: running_count,
            schedulers.INST_ECS_ORG_DESIRED_COUNT: org_desired_count,
            schedulers.INST_ALLOW_RESIZE: self.allow_resize,
            schedulers.INST_HIBERNATE: False,
            schedulers.INST_STATE: status,
            schedulers.INST_STATE_NAME: status,
            schedulers.INST_IS_RUNNING: is_running,
            schedulers.INST_IS_TERMINATED: False,
            schedulers.INST_CURRENT_STATE: InstanceSchedule.STATE_RUNNING if is_running else InstanceSchedule.STATE_STOPPED,
            schedulers.INST_TAGS: tags,
            schedulers.INST_NAME: ecs_service["serviceName"],
            schedulers.INST_SCHEDULE: schedule,
            schedulers.INST_INSTANCE_TYPE: ecs_service["launchType"],
            schedulers.INST_MAINTENANCE_WINDOW: None
        }
        return instance_data

    def resize_instance(self, kwargs):
        """Resizes an instance. NOT IMPLEMENTED FOR ECS SERVICE.
        """
        pass

    # noinspection PyMethodMayBeStatic
    def stop_instances(self, kwargs):
        """Stop the ECS Services referenced in stopped_instances.

        Args:
            stopped_instances (list): The list of ECS services to be stopped

        Yields:
            str: The ECS Service ARN
        """

        self._init_scheduler(kwargs)
        client = self._get_client()

        for ecs_service in kwargs["stopped_instances"]:
            try:
                client.update_service(
                    cluster=ecs_service.cluster_arn,
                    service=ecs_service.name,
                    desiredCount=0)
                self._tag_stopped_resource(client, ecs_service)
                yield ecs_service.id, InstanceSchedule.STATE_STOPPED
            except Exception as ex:
                self._logger.error("Error scaling in ECS Service {}, ({})",
                                   ecs_service.name,
                                   str(ex))

    # noinspection PyMethodMayBeStatic
    def start_instances(self, kwargs):
        """Stop the ECS Services referenced in started_instances.

        Args:
            started_instances (list): The list of ECS services to be stared

        Yields:
            str: The ECS Service ARN
        """
        self._init_scheduler(kwargs)
        client = self._get_client()

        for ecs_service in kwargs["started_instances"]:
            try:
                client.update_service(
                    cluster=ecs_service.cluster_arn,
                    service=ecs_service.name,
                    desiredCount=int(ecs_service.org_desired_count))
                self._tag_started_instances(client, ecs_service)
                yield ecs_service.id, InstanceSchedule.STATE_RUNNING
            except Exception as ex:
                self._logger.error("Error scaling out ECS Service {} ({})",
                                   ecs_service.name,
                                   str(ex))
        return

    def _tag_stopped_resource(self, client, ecs_service):
        self._tag_resource(client,
                           ecs_service,
                           self._config.stopped_tags,
                           self._config.started_tags)
        # Adding tag self.DESIRED_COUNT_TAG_NAME
        client.tag_resource(
            resourceArn=ecs_service.id,
            tags=[{
                'key': self.DESIRED_COUNT_TAG_NAME,
                'value': str(ecs_service.desired_count)
            }]
        )

    def _tag_started_instances(self, client, ecs_service):
        self._tag_resource(client,
                           ecs_service,
                           self._config.started_tags,
                           self._config.stopped_tags)
        # Adding tag self.DESIRED_COUNT_TAG_NAME
        client.untag_resource(
            resourceArn=ecs_service.id,
            tagKeys=[self.DESIRED_COUNT_TAG_NAME]
        )

    def _validate_rds_tag_values(self, tags):
        result = copy.deepcopy(tags)
        for t in result:
            original_value = t.get("Value", "")
            value = re.sub(
                RESTRICTED_RDS_TAG_VALUE_SET_CHARACTERS, " ", original_value)
            value = value.replace("\n", " ")
            if value != original_value:
                self._logger.warning(WARN_RDS_TAG_VALUE,
                                     original_value, t, value)
                t["Value"] = value
            t["value"] = t["Value"]
            t["key"] = t["Key"]
            del t["Value"]
            del t["Key"]
        return result

    def _tag_resource(self, client, ecs_service, new_config_tags, old_config_tags):
        new_tags = self._validate_rds_tag_values(new_config_tags)
        if new_tags is None:
            new_tags = []
        new_tags_keys = [t["key"] for t in new_tags]
        old_tags_keys = [t["key"]
                         for t in old_config_tags if t["Key"] not in new_tags_keys]

        try:
            if old_tags_keys is not None and len(old_tags_keys):
                # TODO: fix the message below. not always "start"
                self._logger.info("Removing {} key(s) {} from ECS Service {}",
                                  "start",
                                  ",".join(["\"{}\"".format(k)
                                           for k in old_tags_keys]),
                                  ecs_service.id)
                client.untag_resource(resourceArn=ecs_service.id,
                                      tagKeys=old_tags_keys)
            if len(new_tags) > 0:
                # TODO: fix the message below. not always "stop"
                self._logger.info("Adding {} tags {} to ECS Service {}",
                                  "stop",
                                  str(new_tags),
                                  ecs_service.id)
                client.tag_resource(resourceArn=ecs_service.id,
                                    tags=new_tags)
        except Exception as ex:
            self._logger.warning("Error setting start or stop tags after scaling operation on service {}, ({})",
                                 ecs_service.name,
                                 str(ex))
