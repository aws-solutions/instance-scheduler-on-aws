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

import schedulers
import re
import copy

from boto_retry import get_client_with_retries

from configuration.instance_schedule import InstanceSchedule
from configuration.running_period import RunningPeriod
from configuration.scheduler_config_builder import SchedulerConfigBuilder
from configuration.setbuilders.weekday_setbuilder import WeekdaySetBuilder

RESTRICTED_RDS_TAG_VALUE_SET_CHARACTERS = r"[^a-zA-Z0-9\s_\.:+/=\\@-]"

RDS_DB_ARN = "arn:aws:rds:{}:{}:db:{}"

ERR_STARTING_INSTANCE = "Error starting rds instance {} ({})"
ERR_STOPPING_INSTANCE = "Error stopping rds instance {}, action : {} ({})"

INF_ADD_TAGS = "Adding {} tags {} to instance {}"
INF_DELETE_SNAPSHOT = "Deleted previous snapshot {}"
INF_FETCHED = "Number of fetched rds  instances is {}, number of instances in a schedulable state is {}"
INF_FETCHING_INSTANCES = "Fetching rds instances for account {} in region {}"
INF_REMOVE_KEYS = "Removing {} key(s) {} from instance {}"
INF_STOPPED_INSTANCE = "Stopped rds instance \"{}\" and creating snapshot \"{}\""

DEBUG_MULTI_AZ = "Can not schedule Multi-AZ or Mirrored database rds instance \"{}\""
DEBUG_UNSUPPORTED_ENGINE = "Engine type {} of rds instance \"{}\" is not supported for scheduling"
DEBUG_READ_REPLICA = "Can not schedule rds instance \"{}\" because it is a read replica of instance {}"
DEBUG_READ_REPLICA_SOURCE = "Can not schedule rds instance \"{}\" because it is the source for read copy instance(s) {}"
DEBUG_SKIPPING_INSTANCE = "Skipping rds instance {} because it is not in a start or stop-able state ({})"
DEBUG_WITHOUT_SCHEDULE = "Skipping rds instance {} without schedule"
DEBUG_SELECTED = "Selected rds instance {} in state ({}) for schedule {}"
DEBUG_NO_SCHEDULE_TAG = "Instance {} has no schedule tag named {}"

WARN_TAGGING_STARTED = "Error setting start or stop tags to started instance {}, ({})"
WARN_TAGGING_STOPPED = "Error setting start or stop tags to stopped instance {}, ({})"
WARN_RDS_TAG_VALUE = "Tag value \"{}\" for tag \"{}\" changed to \"{}\" because it did contain characters that are not allowed " \
                     "in RDS tag values. The value can only contain only the set of Unicode letters, digits, " \
                     "white-space, '_', '.', '/', '=', '+', '-'"

MAINTENANCE_SCHEDULE_NAME = "Preferred Maintenance Window Schedule"
MAINTENANCE_PERIOD_NAME = "Preferred Maintenance Window Period"


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
        self._tagname = args.get(schedulers.PARAM_TAG_NAME)
        self._config = args.get(schedulers.PARAM_CONFIG)
        self._instance_tags = None

    @property
    def instance_tags(self):

        if self._instance_tags is None:
            tag_client = get_client_with_retries("resourcegroupstaggingapi",
                                                 methods=["get_resources"],
                                                 session=self._session,
                                                 context=self._context,
                                                 region=self._region)

            args = {
                "TagFilters": [{"Key": self._tagname}],
                "ResourcesPerPage": 50,
                "ResourceTypeFilters": ["rds:db"]
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

    def get_schedulable_instances(self, kwargs):

        def is_schedulable(rds_inst):

            db_id = rds_inst["DBInstanceIdentifier"]

            state = rds_inst["DBInstanceStatus"]

            if state not in RdsService.RDS_SCHEDULABLE_STATES:
                self._logger.debug(DEBUG_SKIPPING_INSTANCE, db_id, state)
                return False

            if rds_inst["MultiAZ"]:
                self._logger.debug(DEBUG_MULTI_AZ.format(db_id))
                return False

            if rds_inst.get("ReadReplicaSourceDBInstanceIdentifier", None) is not None:
                self._logger.debug(DEBUG_READ_REPLICA, db_id, rds_inst["ReadReplicaSourceDBInstanceIdentifier"])
                return False

            if len(rds_inst.get("ReadReplicaDBInstanceIdentifiers", [])) > 0:
                self._logger.debug(DEBUG_READ_REPLICA_SOURCE, db_id, ",".join(rds_inst["ReadReplicaDBInstanceIdentifiers"]))
                return False

            if rds_inst["Engine"] in ["aurora"]:
                self._logger.debug(DEBUG_UNSUPPORTED_ENGINE, rds_inst["Engine"], db_id)
                return False

            if self.instance_tags.get(instance["DBInstanceArn"]) is None:
                self._logger.debug(DEBUG_NO_SCHEDULE_TAG, rds_inst, self._tagname)
                return False

            return True

        self._init_scheduler(kwargs)

        methods = ["describe_db_instances"]
        client = get_client_with_retries("rds", methods, context=self._context, session=self._session, region=self._region)

        describe_arguments = {}
        instances = []
        number_of_instances = 0
        self._logger.info(INF_FETCHING_INSTANCES, self._account, self._region)

        while True:
            self._logger.debug("Making describe_db_instances call with parameters {}", describe_arguments)
            rds_resp = client.describe_db_instances_with_retries(**describe_arguments)
            for instance in rds_resp["DBInstances"]:
                number_of_instances += 1

                if is_schedulable(instance):

                    instance_data = self._select_instance_data(instance=instance)

                    schedule_name = instance_data[schedulers.INST_SCHEDULE]
                    if schedule_name not in [None, ""]:
                        self._logger.debug(DEBUG_SELECTED, instance_data[schedulers.INST_ID],
                                           instance_data[schedulers.INST_STATE_NAME],
                                           schedule_name)
                        instances.append(instance_data)
                    else:
                        self._logger.debug(DEBUG_WITHOUT_SCHEDULE, instance_data[schedulers.INST_ID])
            if "Marker" in rds_resp:
                describe_arguments["Marker"] = rds_resp["Marker"]
            else:
                break
        self._logger.info(INF_FETCHED, number_of_instances, len(instances))
        return instances

    def _select_instance_data(self, instance):

        tags = self.instance_tags.get(instance["DBInstanceArn"], {})

        state = instance["DBInstanceStatus"]

        is_running = state == self.RDS_STATE_AVAILABLE

        instance_data = {
            schedulers.INST_ID: instance["DBInstanceIdentifier"],
            schedulers.INST_ALLOW_RESIZE: self.allow_resize,
            schedulers.INST_STATE: state,
            schedulers.INST_STATE_NAME: state,
            schedulers.INST_IS_RUNNING: is_running,
            schedulers.INST_IS_TERMINATED: False,
            schedulers.INST_CURRENT_STATE: InstanceSchedule.STATE_RUNNING if is_running else InstanceSchedule.STATE_STOPPED,
            schedulers.INST_INSTANCE_TYPE: instance["DBInstanceClass"],
            schedulers.INST_ENGINE_TYPE: instance["Engine"],
            schedulers.INST_MAINTENANCE_WINDOW: RdsService.build_schedule_from_maintenance_window(
                instance["PreferredMaintenanceWindow"]),
            schedulers.INST_TAGS: tags,
            schedulers.INST_NAME: tags.get("Name", ""),
            schedulers.INST_SCHEDULE: tags.get(self._tagname, None)
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

    # noinspection PyMethodMayBeStatic
    def stop_instances(self, kwargs):

        def does_snapshot_exist(name):

            try:
                resp = client.describe_db_snapshots_with_retries(DBSnapshotIdentifier=name, SnapshotType="manual")
                snapshot = resp.get("DBSnapshots", None)
                return snapshot is not None
            except Exception as e:
                if type(e).__name__ == "DBSnapshotNotFoundFault":
                    return False
                else:
                    raise ex

        self._init_scheduler(kwargs)

        methods = ["stop_db_instance",
                   "describe_db_snapshots",
                   "delete_db_snapshot",
                   "add_tags_to_resource",
                   "remove_tags_from_resource"]

        client = get_client_with_retries("rds", methods, context=self._context, session=self._session, region=self._region)

        stop_tags = self._validate_rds_tag_values(self._config.stopped_tags)
        start_tags_keys = [t["Key"] for t in self._config.started_tags]

        stopped_instances = kwargs["stopped_instances"]

        action = ""

        for inst in stopped_instances:
            try:

                arn = RDS_DB_ARN.format(inst.region, inst.account, inst.id)
                snapshot_name = "{}-stopped-{}".format(self._stack_name, inst.id).replace(" ", "")

                action = "describe_db_snapshots"
                if does_snapshot_exist(snapshot_name):
                    action = "delete_db_snapshot"
                    client.delete_db_snapshot_with_retries(DBSnapshotIdentifier=snapshot_name)
                    self._logger.info(INF_DELETE_SNAPSHOT, snapshot_name)

                action = "stop_db_instance"
                client.stop_db_instance_with_retries(DBInstanceIdentifier=inst.id, DBSnapshotIdentifier=snapshot_name)
                self._logger.info(INF_STOPPED_INSTANCE, inst.id, snapshot_name)

                try:
                    if start_tags_keys is not None and len(start_tags_keys):
                        self._logger.info(INF_REMOVE_KEYS, "start",
                                          ",".join(["\"{}\"".format(k) for k in start_tags_keys]), arn)
                        client.remove_tags_from_resource_with_retries(ResourceName=arn, TagKeys=start_tags_keys)
                    if stop_tags is not None and len(stop_tags) > 0:
                        self._logger.info(INF_ADD_TAGS, "stop", str(stop_tags), arn)
                        client.add_tags_to_resource_with_retries(ResourceName=arn, Tags=stop_tags)
                except Exception as ex:
                    self._logger.warning(WARN_TAGGING_STOPPED, inst.id, str(ex))

                yield inst.id, InstanceSchedule.STATE_STOPPED
            except Exception as ex:
                self._logger.error(ERR_STOPPING_INSTANCE, inst.instance_str, action, str(ex))
                return

    # noinspection PyMethodMayBeStatic
    def start_instances(self, kwargs):
        self._init_scheduler(kwargs)

        methods = ["start_db_instance",
                   "add_tags_to_resource",
                   "remove_tags_from_resource"]

        client = get_client_with_retries("rds", methods, context=self._context, session=self._session, region=self._region)

        start_tags = self._validate_rds_tag_values(kwargs[schedulers.PARAM_CONFIG].started_tags)
        stop_tags_keys = [t["Key"] for t in self._config.stopped_tags]

        started_instances = kwargs["started_instances"]
        for inst in started_instances:
            arn = RDS_DB_ARN.format(inst.region, inst.account, inst.id)
            try:
                client.start_db_instance_with_retries(DBInstanceIdentifier=inst.id)

                try:
                    if stop_tags_keys is not None and len(stop_tags_keys):
                        self._logger.info(INF_REMOVE_KEYS, "stop",
                                          ",".join(["\"{}\"".format(k) for k in stop_tags_keys]), arn)
                        client.remove_tags_from_resource_with_retries(ResourceName=arn, TagKeys=stop_tags_keys)
                    if start_tags is not None and len(start_tags) > 0:
                        self._logger.info(INF_ADD_TAGS, "start", str(start_tags), arn)
                        client.add_tags_to_resource_with_retries(ResourceName=arn, Tags=start_tags)
                except Exception as ex:
                    self._logger.warning(WARN_TAGGING_STARTED, inst.id, str(ex))

                yield inst.id, InstanceSchedule.STATE_RUNNING
            except Exception as ex:
                self._logger.error(ERR_STARTING_INSTANCE, inst.instance_str, str(ex))
                return
