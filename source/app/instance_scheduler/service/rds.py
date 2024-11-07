# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import re
from collections.abc import Iterator, Sequence
from datetime import date, datetime, time, timedelta
from functools import cached_property
from itertools import chain
from typing import TYPE_CHECKING, Any, Final, Optional, TypedDict
from zoneinfo import ZoneInfo

from instance_scheduler.boto_retry import get_client_with_standard_retry
from instance_scheduler.configuration.instance_schedule import InstanceSchedule
from instance_scheduler.configuration.running_period import RunningPeriod
from instance_scheduler.configuration.running_period_dict_element import (
    RunningPeriodDictElement,
)
from instance_scheduler.configuration.scheduling_context import (
    SchedulingContext,
    TagTemplate,
)
from instance_scheduler.configuration.time_utils import parse_time_str
from instance_scheduler.cron.cron_recurrence_expression import CronRecurrenceExpression
from instance_scheduler.cron.parser import parse_weekdays_expr
from instance_scheduler.handler.environments.scheduling_request_environment import (
    SchedulingRequestEnvironment,
)
from instance_scheduler.schedulers.states import ScheduleState
from instance_scheduler.service import Service
from instance_scheduler.service.rds_instance import RdsInstance
from instance_scheduler.util.logger import Logger
from instance_scheduler.util.pagination import paginate
from instance_scheduler.util.session_manager import AssumedRole

if TYPE_CHECKING:
    from mypy_boto3_rds.client import RDSClient
    from mypy_boto3_rds.type_defs import DBClusterTypeDef, DBInstanceTypeDef, TagTypeDef
    from mypy_boto3_resourcegroupstaggingapi.client import (
        ResourceGroupsTaggingAPIClient,
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

MAINTENANCE_SCHEDULE_NAME = "RDS preferred Maintenance Window Schedule"
MAINTENANCE_PERIOD_NAME = "RDS preferred Maintenance Window Period"
RDS_CLUSTER_ENGINES: Final = frozenset(
    {"aurora-mysql", "aurora-postgresql", "neptune", "docdb"}
)

ResourceArn = str


class RdsTagDescription(TypedDict):
    db: dict[ResourceArn, dict[str, str]]
    cluster: dict[ResourceArn, dict[str, str]]


class RdsService(Service[RdsInstance]):
    RDS_STATE_AVAILABLE = "available"
    RDS_STATE_STOPPED = "stopped"

    RDS_SCHEDULABLE_STATES = {RDS_STATE_AVAILABLE, RDS_STATE_STOPPED}

    def __init__(
        self,
        assumed_scheduling_role: AssumedRole,
        logger: Logger,
        scheduling_context: SchedulingContext,
        env: SchedulingRequestEnvironment,
    ) -> None:
        self._rds_client: Final = get_client_with_standard_retry(
            "rds",
            session=assumed_scheduling_role.session,
            region=assumed_scheduling_role.region,
        )
        self._rgta_client: Final = get_client_with_standard_retry(
            "resourcegroupstaggingapi",
            session=assumed_scheduling_role.session,
            region=assumed_scheduling_role.region,
        )

        self._logger: Final = logger
        self._scheduling_context: Final = scheduling_context
        self._stack_name: Final = env.stack_name
        self._env: Final = env

        self._instance_tags: Optional[dict[str, dict[str, dict[str, str]]]] = None

        self._enabled_services = []
        if self._env.enable_rds_service:
            self._enabled_services.append("rds:db")  # NOSONAR

        if (
            self._env.enable_rds_clusters
            or self._env.enable_docdb_service
            or self._env.enable_neptune_service
        ):
            self._enabled_services.append("rds:cluster")  # NOSONAR

    @property
    def service_name(self) -> str:
        return "rds"

    @cached_property
    def rds_resource_tags(self) -> RdsTagDescription:
        instance_tags: RdsTagDescription = {"db": {}, "cluster": {}}

        paginator: Final = self._rgta_client.get_paginator("get_resources")
        if "rds:db" in self._enabled_services:  # NOSONAR
            for page in paginator.paginate(
                TagFilters=[{"Key": self._env.schedule_tag_key}],
                ResourceTypeFilters=["rds:db"],  # NOSONAR
            ):
                for resource in page["ResourceTagMappingList"]:
                    arn = resource["ResourceARN"]
                    instance_tags["db"][arn] = {
                        tag["Key"]: tag["Value"]
                        for tag in resource.get("Tags", {})
                        if tag["Key"] in {"Name", self._env.schedule_tag_key}
                    }

        if "rds:cluster" in self._enabled_services:  # NOSONAR
            for page in paginator.paginate(
                TagFilters=[{"Key": self._env.schedule_tag_key}],
                ResourceTypeFilters=["rds:cluster"],  # NOSONAR
            ):
                for resource in page["ResourceTagMappingList"]:
                    arn = resource["ResourceARN"]
                    instance_tags["cluster"][arn] = {
                        tag["Key"]: tag["Value"]
                        for tag in resource.get("Tags", {})
                        if tag["Key"] in {"Name", self._env.schedule_tag_key}
                    }

        return instance_tags

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

        start_weekday_expr = parse_weekdays_expr({start_day_string})
        start_time = parse_time_str(start_hhmm_string)
        end_time = parse_time_str(stop_hhmm_string)

        # start 10 minutes early
        # note: python can only subtract timedeltas from datetimes
        adjusted_start_time = (
            datetime.combine(date.today(), start_time) - timedelta(minutes=10)
        ).time()

        if start_time >= time(0, 10):
            start_time = adjusted_start_time
        else:
            # delta will cross midnight
            days_strings = ["sun", "mon", "tue", "wed", "thu", "fri", "sat", "sun"]
            index = days_strings.index(start_day_string, 1)
            adjusted_start_day = days_strings[index - 1]

            start_day_string = adjusted_start_day
            start_weekday_expr = parse_weekdays_expr({adjusted_start_day})
            start_time = adjusted_start_time

        # windows that do not overlap days only require one period for schedule
        if start_day_string == stop_day_string:
            periods: list[RunningPeriodDictElement] = [
                {
                    "period": RunningPeriod(
                        name=MAINTENANCE_PERIOD_NAME,
                        begintime=start_time,
                        endtime=end_time,
                        cron_recurrence=CronRecurrenceExpression(
                            weekdays=start_weekday_expr
                        ),
                    )
                }
            ]
        else:
            # windows that overlap days require two periods for schedule
            end_time_day1 = parse_time_str("23:59")
            begin_time_day2 = parse_time_str("00:00")
            stop_weekday_expr = parse_weekdays_expr({stop_day_string})
            periods = [
                {
                    "period": RunningPeriod(
                        name=MAINTENANCE_PERIOD_NAME + "-{}".format(start_day_string),
                        begintime=start_time,
                        endtime=end_time_day1,
                        cron_recurrence=CronRecurrenceExpression(
                            weekdays=start_weekday_expr
                        ),
                    ),
                    "instancetype": None,
                },
                {
                    "period": RunningPeriod(
                        name=MAINTENANCE_PERIOD_NAME + "-{}".format(stop_day_string),
                        begintime=begin_time_day2,
                        endtime=end_time,
                        cron_recurrence=CronRecurrenceExpression(
                            weekdays=stop_weekday_expr,
                        ),
                    ),
                    "instancetype": None,
                },
            ]

        # create schedule with period(s) and timezone UTC
        schedule = InstanceSchedule(
            name=MAINTENANCE_SCHEDULE_NAME,
            periods=periods,
            timezone=ZoneInfo("UTC"),  # PreferredMaintenanceWindow field is in utc
            # https://docs.aws.amazon.com/cli/latest/reference/rds/describe-db-instances.html
            enforced=True,
        )

        return schedule

    def instance_is_in_scope(self, rds_inst: DBInstanceTypeDef) -> bool:
        """check whether the instance is within scope for scheduling"""
        db_id = rds_inst["DBInstanceIdentifier"]
        db_arn = rds_inst["DBInstanceArn"]
        db_tags: dict[str, str] = self.rds_resource_tags["db"].get(db_arn, {})

        if not db_tags.get(self._env.schedule_tag_key, None):
            self._logger.debug(
                f"Rds instance {rds_inst} has no attached schedule using the schedule tag: {self._env.schedule_tag_key}"
            )
            return False

        if rds_inst.get("ReadReplicaSourceDBInstanceIdentifier", None):
            self._logger.debug(
                f'Cannot schedule rds instance "{db_id}" because it is a read replica of instance {rds_inst["ReadReplicaSourceDBInstanceIdentifier"]}'
            )
            return False

        if len(rds_inst.get("ReadReplicaDBInstanceIdentifiers", [])) > 0:
            self._logger.debug(
                f'Cannot schedule rds instance "{db_id}" because it is the source for read copy instance(s) {",".join(rds_inst["ReadReplicaDBInstanceIdentifiers"])}'
            )
            return False

        if rds_inst["Engine"] in RDS_CLUSTER_ENGINES:
            self._logger.debug(
                f"Skipping rds instance {db_id} because its engine ({rds_inst['Engine']}) indicates it is a member of a cluster"
            )
            return False

        return True

    def cluster_is_in_scope(self, rds_cluster: DBClusterTypeDef) -> bool:
        """check whether the cluster is within scope for scheduling"""
        cluster_id = rds_cluster["DBClusterIdentifier"]
        cluster_arn = rds_cluster["DBClusterArn"]
        engine = rds_cluster["Engine"]
        cluster_tags: dict[str, str] = self.rds_resource_tags["cluster"].get(
            cluster_arn, {}
        )

        if not cluster_tags.get(self._env.schedule_tag_key, None):
            self._logger.debug(
                f"Rds cluster {rds_cluster} has no attached schedule using the schedule tag: {self._env.schedule_tag_key}"
            )
            return False

        match engine:
            case "neptune":
                if not self._env.enable_neptune_service:
                    self._logger.debug(
                        "Skipping cluster {} - neptune scheduling is not enabled",
                        cluster_id,
                    )
                    return False
            case "docdb":
                if not self._env.enable_docdb_service:
                    self._logger.debug(
                        "Skipping cluster {} - docdb scheduling is not enabled",
                        cluster_id,
                    )
                    return False
            case _:
                if not self._env.enable_rds_clusters:
                    self._logger.debug(
                        "Skipping cluster {} - rds cluster scheduling is not enabled",
                        cluster_id,
                    )
                    return False

        return True

    def get_in_scope_rds_instances(self) -> Iterator[RdsInstance]:
        tagged_instances: dict[ResourceArn, dict[str, str]] = self.rds_resource_tags[
            "db"
        ]
        if not tagged_instances:
            return

        instance_arns = list(tagged_instances.keys())

        paginator = self._rds_client.get_paginator("describe_db_instances")
        for arn_page in paginate(instance_arns, 50):
            for page in paginator.paginate(
                Filters=[
                    {
                        "Name": "db-instance-id",
                        "Values": arn_page,
                    },
                ],
                PaginationConfig={"PageSize": 50},
            ):
                for instance in page.get("DBInstances", []):
                    if self.instance_is_in_scope(instance):
                        rds_instance = self._parse_as_rds_instance(
                            rds_resource=instance,
                            is_cluster=False,
                        )
                        self._logger.debug(
                            f"Selected rds instance {rds_instance.id} in state ({rds_instance.current_state}) for schedule {rds_instance.schedule_name}",
                        )
                        yield rds_instance

    def get_in_scope_rds_clusters(self) -> Iterator[RdsInstance]:
        tagged_clusters: dict[ResourceArn, dict[str, str]] = self.rds_resource_tags[
            "cluster"
        ]
        if not tagged_clusters:
            return

        # get all arns from instance_resources
        cluster_arns = list(tagged_clusters.keys())
        paginator = self._rds_client.get_paginator("describe_db_clusters")

        for arn_page in paginate(cluster_arns, 50):
            for page in paginator.paginate(
                Filters=[
                    {
                        "Name": "db-cluster-id",
                        "Values": arn_page,
                    },
                ],
                PaginationConfig={"PageSize": 50},
            ):
                for cluster in page.get("DBClusters", []):
                    if self.cluster_is_in_scope(cluster):
                        rds_instance = self._parse_as_rds_instance(
                            rds_resource=cluster,
                            is_cluster=True,
                        )
                        self._logger.debug(
                            f"Selected rds cluster {rds_instance.id} in state ({rds_instance.current_state}) for schedule {rds_instance.schedule_name}"
                        )
                        yield rds_instance

    def describe_tagged_instances(self) -> Iterator[RdsInstance]:
        rds_instances = self.get_in_scope_rds_instances()
        rds_clusters = self.get_in_scope_rds_clusters()
        return chain(rds_instances, rds_clusters)

    def _parse_as_rds_instance(
        self, rds_resource: Any, is_cluster: bool
    ) -> RdsInstance:
        # type of rds_resource is actually DBInstanceTypeDef | DBClusterTypeDef
        arn_for_tags = (
            rds_resource["DBInstanceArn"]
            if not is_cluster
            else rds_resource["DBClusterArn"]
        )
        if is_cluster:
            tags: dict[str, str] = self.rds_resource_tags["cluster"].get(
                arn_for_tags, {}
            )
        else:
            tags = self.rds_resource_tags["db"].get(arn_for_tags, {})

        state = (
            rds_resource["DBInstanceStatus"]
            if not is_cluster
            else rds_resource["Status"]
        )

        instance_data = RdsInstance(
            _id=(
                rds_resource["DBInstanceIdentifier"]
                if not is_cluster
                else rds_resource["DBClusterIdentifier"]
            ),
            _arn=(
                rds_resource["DBInstanceArn"]
                if not is_cluster
                else rds_resource["DBClusterArn"]
            ),
            _current_state=state,
            _instance_type=(
                rds_resource["DBInstanceClass"] if not is_cluster else "cluster"
            ),
            _engine_type=rds_resource["Engine"],
            _maintenance_windows=[
                RdsService.build_schedule_from_maintenance_window(
                    rds_resource["PreferredMaintenanceWindow"]
                )
            ],
            _tags=tags,
            _name=tags.get("Name", ""),
            _schedule_name=tags.get(self._env.schedule_tag_key, ""),
            _is_cluster=is_cluster,
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
                self._logger.warning(
                    'Tag value "{}" for tag "{}" changed to "{}" because it did contain characters that are not '
                    "allowed "
                    "in RDS tag values. The value can only contain only the set of Unicode letters, digits, "
                    "white-space, '_', '.', '/', '=', '+', '-'",
                    original_value,
                    tag,
                    value,
                )
            result.append({"Key": tag["Key"], "Value": value})
        return result

    def _stop_instance(self, inst: RdsInstance) -> None:
        def does_snapshot_exist(name: str) -> bool:
            try:
                resp = self._rds_client.describe_db_snapshots(
                    DBSnapshotIdentifier=name, SnapshotType="manual"
                )
                snapshot = resp.get("DBSnapshots", None)
                return snapshot is not None
            except Exception as ex:
                if type(ex).__name__ == "DBSnapshotNotFoundFault":
                    return False
                else:
                    raise ex

        args = {"DBInstanceIdentifier": inst.id}

        if self._env.enable_rds_snapshots:
            snapshot_name = "{}-stopped-{}".format(self._stack_name, inst.id).replace(
                " ", ""
            )
            args["DBSnapshotIdentifier"] = snapshot_name

            try:
                if does_snapshot_exist(snapshot_name):
                    self._rds_client.delete_db_snapshot(
                        DBSnapshotIdentifier=snapshot_name
                    )
                    self._logger.info("Deleted previous snapshot {}", snapshot_name)
            except Exception:
                self._logger.error("Error deleting snapshot {}", snapshot_name)

        self._rds_client.stop_db_instance(**args)  # exception caught upstream

    def _tag_stopped_resource(self, rds_resource: RdsInstance) -> None:
        stop_tags = self._validate_rds_tag_values(self._scheduling_context.stopped_tags)
        if stop_tags is None:
            stop_tags = []
        stop_tags_key_names = {t["Key"] for t in stop_tags}

        start_tags_keys = [
            t["Key"]
            for t in self._scheduling_context.started_tags
            if t["Key"] not in stop_tags_key_names
        ]

        try:
            if len(start_tags_keys):
                self._logger.info(
                    "Removing start key(s) {} from instance {}",
                    ",".join(['"{}"'.format(k) for k in start_tags_keys]),
                    rds_resource.arn,
                )
                self._rds_client.remove_tags_from_resource(
                    ResourceName=rds_resource.arn, TagKeys=start_tags_keys
                )
            if len(stop_tags) > 0:
                self._logger.info(
                    "Adding stop tags {} to instance {}",
                    str(stop_tags),
                    rds_resource.arn,
                )
                self._rds_client.add_tags_to_resource(
                    ResourceName=rds_resource.arn, Tags=stop_tags
                )
        except Exception as ex:
            self._logger.warning(
                "Error setting start or stop tags to stopped instance {}, ({})",
                rds_resource.id,
                str(ex),
            )

    def _tag_started_instances(self, rds_resource: RdsInstance) -> None:
        start_tags = self._validate_rds_tag_values(
            self._scheduling_context.started_tags
        )
        if start_tags is None:
            start_tags = []
        start_tags_key_names = {t["Key"] for t in start_tags}

        stop_tags_keys = [
            t["Key"]
            for t in self._scheduling_context.stopped_tags
            if t["Key"] not in start_tags_key_names
        ]
        try:
            if len(stop_tags_keys):
                self._logger.info(
                    "Removing stop key(s) {} from instance {}",
                    ",".join(['"{}"'.format(k) for k in stop_tags_keys]),
                    rds_resource.arn,
                )
                self._rds_client.remove_tags_from_resource(
                    ResourceName=rds_resource.arn, TagKeys=stop_tags_keys
                )
            if start_tags is not None and len(start_tags) > 0:
                self._logger.info(
                    "Adding start tags {} to instance {}",
                    str(start_tags),
                    rds_resource.arn,
                )
                self._rds_client.add_tags_to_resource(
                    ResourceName=rds_resource.arn, Tags=start_tags
                )
        except Exception as ex:
            self._logger.warning(
                "Error setting start or stop tags to started instance {}, ({})",
                rds_resource.id,
                str(ex),
            )

    def stop_instances(
        self, instances_to_stop: list[RdsInstance]
    ) -> Iterator[tuple[str, ScheduleState]]:
        for instance in instances_to_stop:
            try:
                if instance.is_cluster:
                    self._rds_client.stop_db_cluster(DBClusterIdentifier=instance.id)
                    self._logger.info('Stopped rds cluster "{}"', instance.id)
                else:
                    self._stop_instance(instance)
                    self._logger.info('Stopped rds instance "{}"', instance.id)

                self._tag_stopped_resource(instance)

                yield instance.id, ScheduleState.STOPPED
            except Exception as ex:
                self._logger.error(
                    "Error stopping rds {} {}, ({})",
                    "cluster" if instance.is_cluster else "instance",
                    instance.display_str,
                    str(ex),
                )

    def start_instances(
        self, instances_to_start: list[RdsInstance]
    ) -> Iterator[tuple[RdsInstance, Exception]]:

        for instance in instances_to_start:
            try:
                if instance.is_cluster:
                    self._rds_client.start_db_cluster(DBClusterIdentifier=instance.id)
                else:
                    self._rds_client.start_db_instance(DBInstanceIdentifier=instance.id)

                self._tag_started_instances(instance)

            except Exception as ex:
                self._logger.error(
                    "Error starting rds {} {} ({})",
                    "cluster" if instance.is_cluster else "instance",
                    instance.display_str,
                    str(ex),
                )

                yield instance, ex
