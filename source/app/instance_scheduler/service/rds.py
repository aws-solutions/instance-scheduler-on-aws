# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import re
from collections.abc import Callable, Iterator, Sequence
from typing import TYPE_CHECKING, Any, Final, Literal, Optional

from instance_scheduler import ScheduleState
from instance_scheduler.boto_retry import get_client_with_standard_retry
from instance_scheduler.configuration.instance_schedule import (
    Instance,
    InstanceSchedule,
)
from instance_scheduler.configuration.running_period import RunningPeriod
from instance_scheduler.configuration.running_period_dict_element import (
    RunningPeriodDictElement,
)
from instance_scheduler.configuration.scheduler_config_builder import (
    SchedulerConfigBuilder,
)
from instance_scheduler.configuration.scheduling_context import TagTemplate
from instance_scheduler.configuration.setbuilders.weekday_setbuilder import (
    WeekdaySetBuilder,
)
from instance_scheduler.service import Service, ServiceArgs

if TYPE_CHECKING:
    from mypy_boto3_rds.client import RDSClient
    from mypy_boto3_rds.type_defs import (
        DBClusterTypeDef,
        DBInstanceTypeDef,
        DescribeDBClustersMessageRequestTypeDef,
        DescribeDBInstancesMessageRequestTypeDef,
        TagTypeDef,
    )
    from mypy_boto3_resourcegroupstaggingapi.client import (
        ResourceGroupsTaggingAPIClient,
    )
    from mypy_boto3_resourcegroupstaggingapi.type_defs import (
        GetResourcesInputRequestTypeDef,
    )
else:
    RDSClient = object
    DBClusterTypeDef = object
    DBInstanceTypeDef = object
    DescribeDBClustersMessageRequestTypeDef = object
    DescribeDBInstancesMessageRequestTypeDef = object
    TagTypeDef = object
    ResourceGroupsTaggingAPIClient = object
    GetResourcesInputRequestTypeDef = object

RESTRICTED_RDS_TAG_VALUE_SET_CHARACTERS = r"[^a-zA-Z0-9\s_\.:+/=\\@-]"

ERR_STARTING_INSTANCE = "Error starting rds {} {} ({})"
ERR_STOPPING_INSTANCE = "Error stopping rds {} {}, ({})"
ERR_DELETING_SNAPSHOT = "Error deleting snapshot {}"

INF_ADD_TAGS = "Adding {} tags {} to instance {}"
INF_DELETE_SNAPSHOT = "Deleted previous snapshot {}"
INF_FETCHED = "Number of fetched rds {} is {}, number of schedulable  resources is {}"
INF_FETCHING_RESOURCES = "Fetching rds {} for account {} in region {}"
INF_REMOVE_KEYS = "Removing {} key(s) {} from instance {}"
INF_STOPPED_RESOURCE = 'Stopped rds {} "{}"'

DEBUG_READ_REPLICA = (
    'Can not schedule rds instance "{}" because it is a read replica of instance {}'
)
DEBUG_READ_REPLICA_SOURCE = 'Can not schedule rds instance "{}" because it is the source for read copy instance(s) {}'
DEBUG_SKIPPING_INSTANCE = (
    "Skipping rds {} {} because it is not in a start or stop-able state ({})"
)
DEBUG_WITHOUT_SCHEDULE = "Skipping rds {} {} without schedule"
DEBUG_SELECTED = "Selected rds instance {} in state ({}) for schedule {}"
DEBUG_NO_SCHEDULE_TAG = "Instance {} has no schedule tag named {}"

WARN_TAGGING_STARTED = "Error setting start or stop tags to started instance {}, ({})"
WARN_TAGGING_STOPPED = "Error setting start or stop tags to stopped instance {}, ({})"
WARN_RDS_TAG_VALUE = (
    'Tag value "{}" for tag "{}" changed to "{}" because it did contain characters that are not allowed '
    "in RDS tag values. The value can only contain only the set of Unicode letters, digits, "
    "white-space, '_', '.', '/', '=', '+', '-'"
)

MAINTENANCE_SCHEDULE_NAME = "RDS preferred Maintenance Window Schedule"
MAINTENANCE_PERIOD_NAME = "RDS preferred Maintenance Window Period"


class RdsService(Service[Instance]):
    RDS_STATE_AVAILABLE = "available"
    RDS_STATE_STOPPED = "stopped"

    RDS_SCHEDULABLE_STATES = {RDS_STATE_AVAILABLE, RDS_STATE_STOPPED}

    def __init__(self, args: ServiceArgs) -> None:
        Service.__init__(self, args)

        self._session: Final = args["session"]
        self._region: Final = self._session.region_name
        self._account: Final = args["account_id"]
        self._logger: Final = args["logger"]
        self._scheduling_context: Final = args["scheduling_context"]
        self._scheduler_tag_key: Final = self._scheduling_context.tag_name
        self._stack_name: Final = args["stack_name"]

        self._instance_tags: Optional[dict[str, dict[str, str]]] = None

    @property
    def service_name(self) -> str:
        return "rds"

    @property
    def allow_resize(self) -> bool:
        return False

    @property
    def rds_resource_tags(self) -> dict[str, dict[str, str]]:
        if self._instance_tags is None:
            tag_client: ResourceGroupsTaggingAPIClient = get_client_with_standard_retry(
                "resourcegroupstaggingapi", session=self._session, region=self._region
            )

            if self._scheduler_tag_key is None:
                raise ValueError("RDS scheduler not initialized properly")

            args: GetResourcesInputRequestTypeDef = {
                "TagFilters": [{"Key": self._scheduler_tag_key}],
                "ResourcesPerPage": 50,
                "ResourceTypeFilters": ["rds:db", "rds:cluster"],
            }

            self._instance_tags = {}

            while True:
                resp = tag_client.get_resources(**args)

                for resource in resp.get("ResourceTagMappingList", []):
                    self._instance_tags[resource["ResourceARN"]] = {
                        tag["Key"]: tag["Value"]
                        for tag in resource.get("Tags", {})
                        if tag["Key"] in ["Name", self._scheduler_tag_key]
                    }

                if resp.get("PaginationToken", "") != "":
                    args["PaginationToken"] = resp["PaginationToken"]
                else:
                    break

        return self._instance_tags

    @staticmethod
    def build_schedule_from_maintenance_window(period_str: str) -> InstanceSchedule:
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
            periods: list[RunningPeriodDictElement] = [
                {
                    "period": RunningPeriod(
                        name=MAINTENANCE_PERIOD_NAME,
                        begintime=start_time,
                        endtime=end_time,
                        weekdays=start_weekday,
                    )
                }
            ]
        else:
            # window with day overlap, need two periods for schedule
            end_time_day1 = SchedulerConfigBuilder.get_time_from_string("23:59")
            begin_time_day2 = SchedulerConfigBuilder.get_time_from_string("00:00")
            stop_weekday = weekdays_builder.build(stop_day_string)
            periods = [
                {
                    "period": RunningPeriod(
                        name=MAINTENANCE_PERIOD_NAME + "-{}".format(start_day_string),
                        begintime=start_time,
                        endtime=end_time_day1,
                        weekdays=start_weekday,
                    ),
                    "instancetype": None,
                },
                {
                    "period": RunningPeriod(
                        name=MAINTENANCE_PERIOD_NAME + "-{}".format(stop_day_string),
                        begintime=begin_time_day2,
                        endtime=end_time,
                        weekdays=stop_weekday,
                    ),
                    "instancetype": None,
                },
            ]

        # create schedule with period(s) and timezone UTC
        schedule = InstanceSchedule(
            name=MAINTENANCE_SCHEDULE_NAME,
            periods=periods,
            timezone="UTC",  # todo: is this even correct?
            enforced=True,
        )

        return schedule

    def get_schedulable_resources(
        self,
        fn_is_schedulable: Callable[[Any], bool],
        fn_describe_name: Literal["describe_db_instances", "describe_db_clusters"],
    ) -> list[Instance]:
        client: RDSClient = get_client_with_standard_retry(
            "rds", session=self._session, region=self._region
        )

        describe_arguments: DescribeDBInstancesMessageRequestTypeDef | DescribeDBClustersMessageRequestTypeDef = (
            {}
        )
        resource_name = fn_describe_name.split("_")[-1]
        resource_name = resource_name[0].upper() + resource_name[1:]
        resources = []
        number_of_resources = 0
        self._logger.info(
            INF_FETCHING_RESOURCES, resource_name, self._account, self._region
        )

        while True:
            self._logger.debug(
                "Making {} call with parameters {}",
                fn_describe_name,
                describe_arguments,
            )
            fn = getattr(client, fn_describe_name)
            rds_resp = fn(**describe_arguments)
            for resource in rds_resp["DB" + resource_name]:
                number_of_resources += 1

                if fn_is_schedulable(resource):
                    resource_data = self._select_resource_data(
                        rds_resource=resource, is_cluster=resource_name == "Clusters"
                    )

                    schedule_name = resource_data["schedule_name"]
                    if schedule_name not in [None, ""]:
                        self._logger.debug(
                            DEBUG_SELECTED,
                            resource_data["id"],
                            resource_data["state_name"],
                            schedule_name,
                        )
                        resources.append(resource_data)
                    else:
                        self._logger.debug(
                            DEBUG_WITHOUT_SCHEDULE,
                            resource_name[:-1],
                            resource_data["id"],
                        )
            if "Marker" in rds_resp:
                describe_arguments["Marker"] = rds_resp["Marker"]
            else:
                break
        self._logger.info(
            INF_FETCHED, resource_name, number_of_resources, len(resources)
        )
        return resources

    def get_schedulable_rds_instances(self) -> list[Instance]:
        def is_schedulable_instance(rds_inst: DBInstanceTypeDef) -> bool:
            db_id = rds_inst["DBInstanceIdentifier"]

            state = rds_inst["DBInstanceStatus"]

            if state not in RdsService.RDS_SCHEDULABLE_STATES:
                self._logger.debug(DEBUG_SKIPPING_INSTANCE, "instance", db_id, state)
                return False

            if rds_inst.get("ReadReplicaSourceDBInstanceIdentifier", None) is not None:
                self._logger.debug(
                    DEBUG_READ_REPLICA,
                    db_id,
                    rds_inst["ReadReplicaSourceDBInstanceIdentifier"],
                )
                return False

            if len(rds_inst.get("ReadReplicaDBInstanceIdentifiers", [])) > 0:
                self._logger.debug(
                    DEBUG_READ_REPLICA_SOURCE,
                    db_id,
                    ",".join(rds_inst["ReadReplicaDBInstanceIdentifiers"]),
                )
                return False

            if rds_inst["Engine"] in {"aurora", "aurora-mysql", "aurora-postgresql"}:
                return False

            if self.rds_resource_tags.get(rds_inst["DBInstanceArn"]) is None:
                self._logger.debug(
                    DEBUG_NO_SCHEDULE_TAG, rds_inst, self._scheduler_tag_key
                )
                return False

            return True

        return self.get_schedulable_resources(
            fn_is_schedulable=is_schedulable_instance,
            fn_describe_name="describe_db_instances",
        )

    def get_schedulable_rds_clusters(self) -> list[Instance]:
        def is_schedulable(cluster_inst: DBClusterTypeDef) -> bool:
            db_id = cluster_inst["DBClusterIdentifier"]

            state = cluster_inst["Status"]

            if state not in RdsService.RDS_SCHEDULABLE_STATES:
                self._logger.debug(DEBUG_SKIPPING_INSTANCE, "cluster", db_id, state)
                return False

            if self.rds_resource_tags.get(cluster_inst["DBClusterArn"]) is None:
                self._logger.debug(
                    DEBUG_NO_SCHEDULE_TAG, cluster_inst, self._scheduler_tag_key
                )
                return False

            return True

        return self.get_schedulable_resources(
            fn_is_schedulable=is_schedulable,
            fn_describe_name="describe_db_clusters",
        )

    def get_schedulable_instances(self) -> list[Instance]:
        instances = self.get_schedulable_rds_instances()
        if self._scheduling_context.schedule_clusters:
            instances += self.get_schedulable_rds_clusters()
        return instances

    def _select_resource_data(self, rds_resource: Any, is_cluster: bool) -> Instance:
        arn_for_tags = (
            rds_resource["DBInstanceArn"]
            if not is_cluster
            else rds_resource["DBClusterArn"]
        )
        tags = self.rds_resource_tags.get(arn_for_tags, {})

        state = (
            rds_resource["DBInstanceStatus"]
            if not is_cluster
            else rds_resource["Status"]
        )

        is_running = state == self.RDS_STATE_AVAILABLE

        if self._scheduler_tag_key is None:
            raise ValueError("RDS scheduler not initialized properly")

        instance_data = Instance(
            id=rds_resource["DBInstanceIdentifier"]
            if not is_cluster
            else rds_resource["DBClusterIdentifier"],
            arn=rds_resource["DBInstanceArn"]
            if not is_cluster
            else rds_resource["DBClusterArn"],
            allow_resize=self.allow_resize,
            hibernate=False,
            state=state,
            state_name=state,
            is_running=is_running,
            is_terminated=False,
            current_state="running" if is_running else "stopped",
            instancetype=rds_resource["DBInstanceClass"]
            if not is_cluster
            else "cluster",
            engine_type=rds_resource["Engine"],
            maintenance_window=RdsService.build_schedule_from_maintenance_window(
                rds_resource["PreferredMaintenanceWindow"]
            ),
            tags=tags,
            name=tags.get("Name", ""),
            schedule_name=tags.get(self._scheduler_tag_key, None),
            is_cluster=is_cluster,
        )
        return instance_data

    def resize_instance(self, _: Any, __: str) -> None:
        """noop"""

    def _validate_rds_tag_values(
        self, tags: Sequence[TagTemplate]
    ) -> Sequence[TagTypeDef]:
        result: Final[list[TagTypeDef]] = []
        for tag in tags:
            original_value = tag.get("Value", "")
            value = re.sub(RESTRICTED_RDS_TAG_VALUE_SET_CHARACTERS, " ", original_value)
            value = value.replace("\n", " ")
            if value != original_value:
                self._logger.warning(WARN_RDS_TAG_VALUE, original_value, tag, value)
            result.append({"Key": tag["Key"], "Value": value})
        return result

    def _stop_instance(self, client: RDSClient, inst: Instance) -> None:
        def does_snapshot_exist(name: str) -> bool:
            try:
                resp = client.describe_db_snapshots(
                    DBSnapshotIdentifier=name, SnapshotType="manual"
                )
                snapshot = resp.get("DBSnapshots", None)
                return snapshot is not None
            except Exception as ex:
                if type(ex).__name__ == "DBSnapshotNotFoundFault":
                    return False
                else:
                    raise ex

        args = {"DBInstanceIdentifier": inst["id"]}

        if self._scheduling_context.create_rds_snapshot:
            snapshot_name = "{}-stopped-{}".format(
                self._stack_name, inst["id"]
            ).replace(" ", "")
            args["DBSnapshotIdentifier"] = snapshot_name

            try:
                if does_snapshot_exist(snapshot_name):
                    client.delete_db_snapshot(DBSnapshotIdentifier=snapshot_name)
                    self._logger.info(INF_DELETE_SNAPSHOT, snapshot_name)
            except Exception:
                self._logger.error(ERR_DELETING_SNAPSHOT, snapshot_name)

        try:
            client.stop_db_instance(**args)
            self._logger.info(INF_STOPPED_RESOURCE, "instance", inst["id"])
        except Exception as ex:
            self._logger.error(
                ERR_STOPPING_INSTANCE, "instance", inst["instance_str"], str(ex)
            )

    def _tag_stopped_resource(self, client: RDSClient, rds_resource: Instance) -> None:
        stop_tags = self._validate_rds_tag_values(self._scheduling_context.stopped_tags)
        if stop_tags is None:
            stop_tags = []
        stop_tags_key_names = [t["Key"] for t in stop_tags]

        start_tags_keys = [
            t["Key"]
            for t in self._scheduling_context.started_tags
            if t["Key"] not in stop_tags_key_names
        ]

        try:
            if len(start_tags_keys):
                self._logger.info(
                    INF_REMOVE_KEYS,
                    "start",
                    ",".join(['"{}"'.format(k) for k in start_tags_keys]),
                    rds_resource["arn"],
                )
                client.remove_tags_from_resource(
                    ResourceName=rds_resource["arn"], TagKeys=start_tags_keys
                )
            if len(stop_tags) > 0:
                self._logger.info(
                    INF_ADD_TAGS, "stop", str(stop_tags), rds_resource["arn"]
                )
                client.add_tags_to_resource(
                    ResourceName=rds_resource["arn"], Tags=stop_tags
                )
        except Exception as ex:
            self._logger.warning(WARN_TAGGING_STOPPED, rds_resource["id"], str(ex))

    def _tag_started_instances(self, client: RDSClient, rds_resource: Instance) -> None:
        start_tags = self._validate_rds_tag_values(
            self._scheduling_context.started_tags
        )
        if start_tags is None:
            start_tags = []
        start_tags_key_names = [t["Key"] for t in start_tags]

        stop_tags_keys = [
            t["Key"]
            for t in self._scheduling_context.stopped_tags
            if t["Key"] not in start_tags_key_names
        ]
        try:
            if len(stop_tags_keys):
                self._logger.info(
                    INF_REMOVE_KEYS,
                    "stop",
                    ",".join(['"{}"'.format(k) for k in stop_tags_keys]),
                    rds_resource["arn"],
                )
                client.remove_tags_from_resource(
                    ResourceName=rds_resource["arn"], TagKeys=stop_tags_keys
                )
            if start_tags is not None and len(start_tags) > 0:
                self._logger.info(
                    INF_ADD_TAGS, "start", str(start_tags), rds_resource["arn"]
                )
                client.add_tags_to_resource(
                    ResourceName=rds_resource["arn"], Tags=start_tags
                )
        except Exception as ex:
            self._logger.warning(WARN_TAGGING_STARTED, rds_resource["id"], str(ex))

    def stop_instances(
        self, instances_to_stop: list[Instance]
    ) -> Iterator[tuple[str, ScheduleState]]:
        client = get_client_with_standard_retry(
            "rds", session=self._session, region=self._region
        )

        for rds_resource in instances_to_stop:
            try:
                if rds_resource["is_cluster"]:
                    client.stop_db_cluster(DBClusterIdentifier=rds_resource["id"])
                    self._logger.info(
                        INF_STOPPED_RESOURCE, "cluster", rds_resource["id"]
                    )
                else:
                    self._stop_instance(client, rds_resource)

                self._tag_stopped_resource(client, rds_resource)

                yield rds_resource["id"], "stopped"
            except Exception as ex:
                self._logger.error(
                    ERR_STOPPING_INSTANCE,
                    "cluster" if rds_resource["is_cluster"] else "instance",
                    rds_resource["instance_str"],
                    str(ex),
                )

    def start_instances(
        self, instances_to_start: list[Instance]
    ) -> Iterator[tuple[str, ScheduleState]]:
        client: RDSClient = get_client_with_standard_retry(
            "rds", session=self._session, region=self._region
        )

        for rds_resource in instances_to_start:
            try:
                if rds_resource["is_cluster"]:
                    client.start_db_cluster(DBClusterIdentifier=rds_resource["id"])
                else:
                    client.start_db_instance(DBInstanceIdentifier=rds_resource["id"])

                self._tag_started_instances(client, rds_resource)

                yield rds_resource["id"], "running"
            except Exception as ex:
                self._logger.error(
                    ERR_STARTING_INSTANCE,
                    "cluster" if rds_resource["is_cluster"] else "instance",
                    rds_resource["instance_str"],
                    str(ex),
                )
