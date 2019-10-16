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

import copy
import re

import schedulers
import re
import copy

from boto_retry import get_client_with_retries
from configuration.instance_schedule import InstanceSchedule
from configuration.running_period import RunningPeriod
from configuration.scheduler_config_builder import SchedulerConfigBuilder
from configuration.setbuilders.weekday_setbuilder import WeekdaySetBuilder

RESTRICTED_RDS_TAG_VALUE_SET_CHARACTERS = r"[^a-zA-Z0-9\s_\.:+/=\\@-]"

ERR_STARTING_INSTANCE = "Error starting rds {} {} ({})"
ERR_STOPPING_INSTANCE = "Error stopping rds {} {}, ({})"
ERR_DELETING_SNAPSHOT = "Error deleting snapshot {}"

INF_ADD_TAGS = "Adding {} tags {} to instance {}"
INF_DELETE_SNAPSHOT = "Deleted previous snapshot {}"
INF_FETCHED = "Number of fetched rds {} is {}, number of schedulable  resources is {}"
INF_FETCHING_RESOURCES = "Fetching rds {} for account {} in region {}"
INF_REMOVE_KEYS = "Removing {} key(s) {} from instance {}"
INF_STOPPED_RESOURCE = "Stopped rds {} \"{}\""

DEBUG_READ_REPLICA = "Can not schedule rds instance \"{}\" because it is a read replica of instance {}"
DEBUG_READ_REPLICA_SOURCE = "Can not schedule rds instance \"{}\" because it is the source for read copy instance(s) {}"
DEBUG_SKIPPING_INSTANCE = "Skipping rds {} {} because it is not in a start or stop-able state ({})"
DEBUG_WITHOUT_SCHEDULE = "Skipping rds {} {} without schedule"
DEBUG_SELECTED = "Selected rds instance {} in state ({}) for schedule {}"
DEBUG_NO_SCHEDULE_TAG = "Instance {} has no schedule tag named {}"

WARN_TAGGING_STARTED = "Error setting start or stop tags to started instance {}, ({})"
WARN_TAGGING_STOPPED = "Error setting start or stop tags to stopped instance {}, ({})"
WARN_RDS_TAG_VALUE = "Tag value \"{}\" for tag \"{}\" changed to \"{}\" because it did contain characters that are not allowed " \
                    "in RDS tag values. The value can only contain only the set of Unicode letters, digits, " \
                     "white-space, '_', '.', '/', '=', '+', '-'"

MAINTENANCE_SCHEDULE_NAME = "RDS preferred Maintenance Window Schedule"
MAINTENANCE_PERIOD_NAME = "RDS preferred Maintenance Window Period"


class RdsService:
    RDS_STATE_AVAILABLE = "available"
    RDS_STATE_STOPPED = "stopped"

    RDS_SCHEDULABLE_STATES = {RDS_STATE_AVAILABLE, RDS_STATE_STOPPED}

    def __init__(self):
        self.service_name = "rds"
        self.allow_resize = False
        self._instance_tags = None

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
        self._account = args.get(schedulers.PARAM_ACCOUNT)
        self._context = args.get(schedulers.PARAM_CONTEXT)
        self._logger = args.get(schedulers.PARAM_LOGGER)
        self._region = args.get(schedulers.PARAM_REGION)
        self._stack_name = args.get(schedulers.PARAM_STACK)
        self._session = args.get(schedulers.PARAM_SESSION)
        self._tagname = args.get(schedulers.PARAM_CONFIG).tag_name
        self._config = args.get(schedulers.PARAM_CONFIG)
        self._instance_tags = None

    @property
    def rds_resource_tags(self):

        if self._instance_tags is None:
            tag_client = get_client_with_retries("resourcegroupstaggingapi",
                                                 methods=["get_resources"],
                                                 session=self._session,
                                                 context=self._context,
                                                 region=self._region)

            args = {
                "TagFilters": [{"Key": self._tagname}],
                "ResourcesPerPage": 50,
                "ResourceTypeFilters": ["rds:db", "rds:cluster"]
            }

            self._instance_tags = {}

            while True:

                resp = tag_client.get_resources_with_retries(**args)

                for resource in resp.get("ResourceTagMappingList", []):
                    self._instance_tags[resource["ResourceARN"]] = {tag["Key"]: tag["Value"]
                                                                    for tag in resource.get("Tags", {})
                                                                    if tag["Key"] in ["Name", self._tagname]}

                if resp.get("PaginationToken", "") != "":
                    args["PaginationToken"] = resp["PaginationToken"]
                else:
                    break

        return self._instance_tags

    @staticmethod
    def build_schedule_from_maintenance_window(period_str):
        """
        Builds a Instance running schedule based on an RDS preferred maintenance windows string in format ddd:hh:mm-ddd:hh:mm
        :param period_str: rds maintenance windows string
        :return: Instance running schedule with timezone UTC
        """

        # get elements of period
        start_string, stop_string = period_str.split("-")
        start_day_string, start_hhmm_string = start_string.split(":", 1)
        stop_day_string, stop_hhmm_string = stop_string.split(":", 1)

        # weekday set builder
        weekdays_builder = WeekdaySetBuilder()

        start_weekday = weekdays_builder.build(start_day_string)
        start_time = SchedulerConfigBuilder.get_time_from_string(start_hhmm_string)
        end_time = SchedulerConfigBuilder.get_time_from_string(stop_hhmm_string)

        # windows with now day overlap, can do with one period for schedule
        if start_day_string == stop_day_string:
            periods = [
                {
                    "period": RunningPeriod(name=MAINTENANCE_PERIOD_NAME,
                                            begintime=start_time,
                                            endtime=end_time,
                                            weekdays=start_weekday)
                }]
        else:
            # window with day overlap, need two periods for schedule
            end_time_day1 = SchedulerConfigBuilder.get_time_from_string("23:59")
            begin_time_day2 = SchedulerConfigBuilder.get_time_from_string("00:00")
            stop_weekday = weekdays_builder.build(stop_day_string)
            periods = [
                {
                    "period": RunningPeriod(name=MAINTENANCE_PERIOD_NAME + "-{}".format(start_day_string),
                                            begintime=start_time,
                                            endtime=end_time_day1,
                                            weekdays=start_weekday),
                    "instancetype": None
                },
                {
                    "period": RunningPeriod(name=MAINTENANCE_PERIOD_NAME + "-{}".format(stop_day_string),
                                            begintime=begin_time_day2,
                                            endtime=end_time,
                                            weekdays=stop_weekday),
                    "instancetype": None
                }]

        # create schedule with period(s) and timezone UTC
        schedule = InstanceSchedule(name=MAINTENANCE_SCHEDULE_NAME, periods=periods, timezone="UTC", enforced=True)

        return schedule

    def get_schedulable_resources(self, fn_is_schedulable, fn_describe_name, kwargs):

        self._init_scheduler(kwargs)

        client = get_client_with_retries("rds", [fn_describe_name], context=self._context, session=self._session,
                                         region=self._region)

        describe_arguments = {}
        resource_name = fn_describe_name.split("_")[-1]
        resource_name = resource_name[0].upper() + resource_name[1:]
        resources = []
        number_of_resources = 0
        self._logger.info(INF_FETCHING_RESOURCES, resource_name, self._account, self._region)

        while True:
            self._logger.debug("Making {} call with parameters {}", fn_describe_name, describe_arguments)
            fn = getattr(client, fn_describe_name + "_with_retries")
            rds_resp = fn(**describe_arguments)
            for resource in rds_resp["DB" + resource_name]:
                number_of_resources += 1

                if fn_is_schedulable(resource):

                    resource_data = self._select_resource_data(rds_resource=resource, is_cluster=resource_name == "Clusters")

                    schedule_name = resource_data[schedulers.INST_SCHEDULE]
                    if schedule_name not in [None, ""]:
                        self._logger.debug(DEBUG_SELECTED, resource_data[schedulers.INST_ID],
                                           resource_data[schedulers.INST_STATE_NAME],
                                           schedule_name)
                        resources.append(resource_data)
                    else:
                        self._logger.debug(DEBUG_WITHOUT_SCHEDULE, resource_name[:-1], resource_data[schedulers.INST_ID])
            if "Marker" in rds_resp:
                describe_arguments["Marker"] = rds_resp["Marker"]
            else:
                break
        self._logger.info(INF_FETCHED, resource_name, number_of_resources, len(resources))
        return resources

    def get_schedulable_rds_instances(self, kwargs):

        def is_schedulable_instance(rds_inst):

            db_id = rds_inst["DBInstanceIdentifier"]

            state = rds_inst["DBInstanceStatus"]

            if state not in RdsService.RDS_SCHEDULABLE_STATES:
                self._logger.debug(DEBUG_SKIPPING_INSTANCE, "instance", db_id, state)
                return False

            if rds_inst.get("ReadReplicaSourceDBInstanceIdentifier", None) is not None:
                self._logger.debug(DEBUG_READ_REPLICA, db_id, rds_inst["ReadReplicaSourceDBInstanceIdentifier"])
                return False

            if len(rds_inst.get("ReadReplicaDBInstanceIdentifiers", [])) > 0:
                self._logger.debug(DEBUG_READ_REPLICA_SOURCE, db_id, ",".join(rds_inst["ReadReplicaDBInstanceIdentifiers"]))
                return False

            if rds_inst["Engine"] in ["aurora"]:
                return False

            if self.rds_resource_tags.get(rds_inst["DBInstanceArn"]) is None:
                self._logger.debug(DEBUG_NO_SCHEDULE_TAG, rds_inst, self._tagname)
                return False

            return True

        return self.get_schedulable_resources(fn_is_schedulable=is_schedulable_instance,
                                              fn_describe_name="describe_db_instances",
                                              kwargs=kwargs)

    def get_schedulable_rds_clusters(self, kwargs):
        def is_schedulable(cluster_inst):

            db_id = cluster_inst["DBClusterIdentifier"]

            state = cluster_inst["Status"]

            if state not in RdsService.RDS_SCHEDULABLE_STATES:
                self._logger.debug(DEBUG_SKIPPING_INSTANCE, "cluster", db_id, state)
                return False

            if self.rds_resource_tags.get(cluster_inst["DBClusterArn"]) is None:
                self._logger.debug(DEBUG_NO_SCHEDULE_TAG, cluster_inst, self._tagname)
                return False

            return True

        return self.get_schedulable_resources(fn_is_schedulable=is_schedulable,
                                              fn_describe_name="describe_db_clusters",
                                              kwargs=kwargs)

    def get_schedulable_instances(self, kwargs):
        instances = self.get_schedulable_rds_instances(kwargs)
        if self._config.schedule_clusters:
            instances += self.get_schedulable_rds_clusters(kwargs)
        return instances

    def _select_resource_data(self, rds_resource, is_cluster):

        arn_for_tags = rds_resource["DBInstanceArn"] if not is_cluster else rds_resource["DBClusterArn"]
        tags = self.rds_resource_tags.get(arn_for_tags, {})

        state = rds_resource["DBInstanceStatus"] if not is_cluster else rds_resource["Status"]

        is_running = state == self.RDS_STATE_AVAILABLE

        instance_data = {
            schedulers.INST_ID: rds_resource["DBInstanceIdentifier"] if not is_cluster else rds_resource["DBClusterIdentifier"],
            schedulers.INST_ARN: rds_resource["DBInstanceArn"] if not is_cluster else rds_resource["DBClusterArn"],
            schedulers.INST_ALLOW_RESIZE: self.allow_resize,
            schedulers.INST_HIBERNATE: False,
            schedulers.INST_STATE: state,
            schedulers.INST_STATE_NAME: state,
            schedulers.INST_IS_RUNNING: is_running,
            schedulers.INST_IS_TERMINATED: False,
            schedulers.INST_CURRENT_STATE: InstanceSchedule.STATE_RUNNING if is_running else InstanceSchedule.STATE_STOPPED,
            schedulers.INST_INSTANCE_TYPE: rds_resource["DBInstanceClass"] if not is_cluster else "cluster",
            schedulers.INST_ENGINE_TYPE: rds_resource["Engine"],
            schedulers.INST_MAINTENANCE_WINDOW: RdsService.build_schedule_from_maintenance_window(
                rds_resource["PreferredMaintenanceWindow"]),
            schedulers.INST_TAGS: tags,
            schedulers.INST_NAME: tags.get("Name", ""),
            schedulers.INST_SCHEDULE: tags.get(self._tagname, None),
            schedulers.INST_DB_IS_CLUSTER: is_cluster
        }
        return instance_data

    def resize_instance(self, kwargs):
        pass

    def _validate_rds_tag_values(self, tags):
        result = copy.deepcopy(tags)
        for t in result:
            original_value = t.get("Value", "")
            value = re.sub(RESTRICTED_RDS_TAG_VALUE_SET_CHARACTERS, " ", original_value)
            value = value.replace("\n", " ")
            if value != original_value:
                self._logger.warning(WARN_RDS_TAG_VALUE, original_value, t, value)
                t["Value"] = value
        return result

    def _stop_instance(self, client, inst):

        def does_snapshot_exist(name):

            try:
                resp = client.describe_db_snapshots_with_retries(DBSnapshotIdentifier=name, SnapshotType="manual")
                snapshot = resp.get("DBSnapshots", None)
                return snapshot is not None
            except Exception as ex:
                if type(ex).__name__ == "DBSnapshotNotFoundFault":
                    return False
                else:
                    raise ex

        args = {
            "DBInstanceIdentifier": inst.id
        }

        if self._config.create_rds_snapshot:
            snapshot_name = "{}-stopped-{}".format(self._stack_name, inst.id).replace(" ", "")
            args["DBSnapshotIdentifier"] = snapshot_name

            try:
                if does_snapshot_exist(snapshot_name):
                    client.delete_db_snapshot_with_retries(DBSnapshotIdentifier=snapshot_name)
                    self._logger.info(INF_DELETE_SNAPSHOT, snapshot_name)
            except Exception as ex:
                self._logger.error(ERR_DELETING_SNAPSHOT, snapshot_name)

        try:
            client.stop_db_instance_with_retries(**args)
            self._logger.info(INF_STOPPED_RESOURCE, "instance", inst.id)
        except Exception as ex:
            self._logger.error(ERR_STOPPING_INSTANCE, "instance", inst.instance_str, str(ex))

    def _tag_stopped_resource(self, client, rds_resource):

        stop_tags = self._validate_rds_tag_values(self._config.stopped_tags)
        if stop_tags is None:
            stop_tags = []
        stop_tags_key_names = [t["Key"] for t in stop_tags]

        start_tags_keys = [t["Key"] for t in self._config.started_tags if t["Key"] not in stop_tags_key_names]

        try:
            if start_tags_keys is not None and len(start_tags_keys):
                self._logger.info(INF_REMOVE_KEYS, "start",
                                  ",".join(["\"{}\"".format(k) for k in start_tags_keys]), rds_resource.arn)
                client.remove_tags_from_resource_with_retries(ResourceName=rds_resource.arn, TagKeys=start_tags_keys)
            if len(stop_tags) > 0:
                self._logger.info(INF_ADD_TAGS, "stop", str(stop_tags), rds_resource.arn)
                client.add_tags_to_resource_with_retries(ResourceName=rds_resource.arn, Tags=stop_tags)
        except Exception as ex:
            self._logger.warning(WARN_TAGGING_STOPPED, rds_resource.id, str(ex))

    def _tag_started_instances(self, client, rds_resource):

        start_tags = self._validate_rds_tag_values(self._config.started_tags)
        if start_tags is None:
            start_tags = []
        start_tags_key_names = [t["Key"] for t in start_tags]

        stop_tags_keys = [t["Key"] for t in self._config.stopped_tags if t["Key"] not in start_tags_key_names]
        try:
            if stop_tags_keys is not None and len(stop_tags_keys):
                self._logger.info(INF_REMOVE_KEYS, "stop",
                                  ",".join(["\"{}\"".format(k) for k in stop_tags_keys]), rds_resource.arn)
                client.remove_tags_from_resource_with_retries(ResourceName=rds_resource.arn, TagKeys=stop_tags_keys)
            if start_tags is not None and len(start_tags) > 0:
                self._logger.info(INF_ADD_TAGS, "start", str(start_tags), rds_resource.arn)
                client.add_tags_to_resource_with_retries(ResourceName=rds_resource.arn, Tags=start_tags)
        except Exception as ex:
            self._logger.warning(WARN_TAGGING_STARTED, rds_resource.id, str(ex))

    # noinspection PyMethodMayBeStatic
    def stop_instances(self, kwargs):

        self._init_scheduler(kwargs)

        methods = ["stop_db_instance",
                   "stop_db_cluster",
                   "describe_db_snapshots",
                   "delete_db_snapshot",
                   "add_tags_to_resource",
                   "remove_tags_from_resource"]

        client = get_client_with_retries("rds", methods, context=self._context, session=self._session, region=self._region)

        stopped_instances = kwargs["stopped_instances"]

        for rds_resource in stopped_instances:
            try:

                if rds_resource.is_cluster:
                    client.stop_db_cluster_with_retries(DBClusterIdentifier=rds_resource.id)
                    self._logger.info(INF_STOPPED_RESOURCE, "cluster", rds_resource.id)
                else:
                    self._stop_instance(client, rds_resource)

                self._tag_stopped_resource(client, rds_resource)

                yield rds_resource.id, InstanceSchedule.STATE_STOPPED
            except Exception as ex:
                self._logger.error(ERR_STOPPING_INSTANCE, "cluster" if rds_resource.is_cluster else "instance",
                                   rds_resource.instance_str, str(ex))

    # noinspection PyMethodMayBeStatic
    def start_instances(self, kwargs):
        self._init_scheduler(kwargs)

        methods = ["start_db_instance",
                   "start_db_cluster",
                   "add_tags_to_resource",
                   "remove_tags_from_resource"]

        client = get_client_with_retries("rds", methods, context=self._context, session=self._session, region=self._region)

        started_instances = kwargs["started_instances"]
        for rds_resource in started_instances:

            try:
                if rds_resource.is_cluster:
                    client.start_db_cluster_with_retries(DBClusterIdentifier=rds_resource.id)
                else:
                    client.start_db_instance_with_retries(DBInstanceIdentifier=rds_resource.id)

                self._tag_started_instances(client, rds_resource)

                yield rds_resource.id, InstanceSchedule.STATE_RUNNING
            except Exception as ex:
                self._logger.error(ERR_STARTING_INSTANCE, "cluster" if rds_resource.is_cluster else "instance",
                                   rds_resource.instance_str, str(ex))
                return
