# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from itertools import batched
from typing import (
    Final,
    Literal,
    Optional,
    Tuple,
    assert_never,
    cast,
)
from zoneinfo import ZoneInfo

from instance_scheduler.configuration.instance_schedule import InstanceSchedule
from instance_scheduler.configuration.running_period import RunningPeriod
from instance_scheduler.configuration.running_period_dict_element import (
    RunningPeriodDictElement,
)
from instance_scheduler.configuration.scheduling_context import (
    SchedulingContext,
)
from instance_scheduler.configuration.time_utils import parse_time_str
from instance_scheduler.cron.cron_recurrence_expression import CronRecurrenceExpression
from instance_scheduler.cron.parser import parse_weekdays_expr
from instance_scheduler.handler.environments.scheduling_request_environment import (
    SchedulingRequestEnvironment,
)
from instance_scheduler.model.managed_instance import RegisteredRdsInstance, RegistryKey
from instance_scheduler.observability.error_codes import ErrorCode
from instance_scheduler.observability.powertools_logging import powertools_logger
from instance_scheduler.scheduling.scheduling_decision import (
    ManagedInstance,
    RequestedAction,
    RuntimeInfo,
    SchedulingDecision,
    make_scheduling_decision,
)
from instance_scheduler.scheduling.scheduling_result import SchedulingResult
from instance_scheduler.scheduling.states import InstanceState
from instance_scheduler.util.arn import ARN
from instance_scheduler.util.session_manager import AssumedRole

RESTRICTED_RDS_TAG_VALUE_SET_CHARACTERS = r"[^a-zA-Z0-9\s_\.:+/=\\@-]"

logger = powertools_logger()


class UnschedulableRDSResource(Exception):
    pass


@dataclass(kw_only=True)
class RdsRuntimeInfo(RuntimeInfo):
    """Runtime information from RDS describe calls"""

    account: str
    region: str
    resource_id: str
    tags: dict[str, str]
    current_state: Literal["available", "stopped", "starting", "stopping"]
    is_cluster: bool
    engine_type: str
    arn: ARN
    preferred_maintenance_window: str
    current_size: str
    name: str

    # extra rds properties that are relevant to determining if the instance is schedulable
    ReadReplicaSourceDBInstanceIdentifier: Optional[str] = None
    ReadReplicaDBInstanceIdentifiers: list[str] = field(default_factory=list)

    @property
    def is_in_schedulable_state(self) -> bool:
        return self.current_state in ["available", "stopped"]

    @property
    def is_running(self) -> bool:
        return self.current_state == "available"

    @property
    def is_stopped(self) -> bool:
        return self.current_state == "stopped"

    @property
    def size(self) -> str:
        return self.current_size

    def to_registry_key(self) -> RegistryKey:
        return RegistryKey.from_arn(self.arn)

    def check_if_is_supported(self) -> Tuple[bool, Optional[str]]:
        """check if rds resource is supported for scheduling. returns true/false and a reason if false"""
        if not self.is_cluster:
            if self.ReadReplicaSourceDBInstanceIdentifier:
                return (
                    False,
                    f"Instance is a read replica of {self.ReadReplicaSourceDBInstanceIdentifier}",
                )

            if self.ReadReplicaDBInstanceIdentifiers:
                return False, "Instance is a source for read replicas"

            if self.engine_type in {
                "aurora-mysql",
                "aurora-postgresql",
                "neptune",
                "docdb",
            }:
                return (
                    False,
                    "Cannot schedule RDS instances that are members of a cluster",
                )

        return True, None


@dataclass(kw_only=True)
class ManagedRdsInstance(ManagedInstance):
    """Composite of registry info and runtime info"""

    registry_info: RegisteredRdsInstance
    runtime_info: RdsRuntimeInfo


class RdsService:

    def __init__(
        self,
        scheduling_context: SchedulingContext,
        env: SchedulingRequestEnvironment,
    ) -> None:
        self.scheduling_context = scheduling_context
        self.rds_client: Final = scheduling_context.assumed_role.client("rds")
        self.stack_name: Final = env.hub_stack_name
        self.env: Final = env

    def schedule_target(self) -> Iterator[SchedulingResult[ManagedRdsInstance]]:
        registry = self.scheduling_context.registry
        registry.preload_cache(
            registry.find_by_scheduling_target(
                account=self.scheduling_context.assumed_role.account,
                region=self.scheduling_context.assumed_role.region,
                service="rds",
            )
        )

        for managed_instance in self.describe_managed_instances():
            schedule = self.scheduling_context.schedule_store.find_by_name(
                managed_instance.registry_info.schedule,
                cache_only=True,
            )

            is_supported, reason = managed_instance.runtime_info.check_if_is_supported()
            if not is_supported:
                yield SchedulingResult.error(
                    resource=managed_instance,
                    error_code=ErrorCode.UNSUPPORTED_RESOURCE,
                    error_message=reason,
                )
                continue

            if schedule is None:
                yield SchedulingResult.error(
                    resource=managed_instance,
                    error_code=ErrorCode.UNKNOWN_SCHEDULE,
                )
                continue

            if not managed_instance.runtime_info.is_in_schedulable_state:
                logger.info(
                    f"Instance {managed_instance.registry_info.resource_id} is not in a schedulable state, skipping"
                )
                yield SchedulingResult.no_action_needed(
                    SchedulingDecision(
                        instance=managed_instance,
                        action=RequestedAction.DO_NOTHING,
                        new_stored_state=managed_instance.registry_info.stored_state,
                        reason=f"Current instance state ({managed_instance.runtime_info.current_state}) is not schedulable",
                    )
                )
                continue

            mws: list[InstanceSchedule] = []
            if schedule.use_maintenance_window:
                mws = [
                    self.build_schedule_from_maintenance_window(
                        managed_instance.runtime_info.preferred_maintenance_window
                    )
                ]

            decision = make_scheduling_decision(
                instance=managed_instance,
                schedule=schedule.to_instance_schedule(
                    self.scheduling_context.period_store
                ),
                current_dt=self.scheduling_context.current_dt,
                maintenance_windows=mws,
            )

            # Process decision immediately (serial processing)
            result = self._process_decision(decision)

            # Update registry if state changed
            if result.instance.registry_info != result.updated_registry_info:
                registry.put(result.updated_registry_info, overwrite=True)

            yield result

    @classmethod
    def describe_tagged_rds_resource_arns(
        cls, assumed_scheduling_role: AssumedRole, tag_key: str
    ) -> Iterator[str]:
        paginator: Final = assumed_scheduling_role.client(
            "resourcegroupstaggingapi"
        ).get_paginator("get_resources")
        for page in paginator.paginate(
            TagFilters=[{"Key": tag_key}],
            ResourceTypeFilters=["rds:db", "rds:cluster"],
        ):
            for resource in page["ResourceTagMappingList"]:
                yield resource["ResourceARN"]

    @classmethod
    def describe_tagged_rds_resources(
        cls, assumed_scheduling_role: AssumedRole, tag_key: str
    ) -> Iterator[RdsRuntimeInfo]:
        resource_arns = list(
            cls.describe_tagged_rds_resource_arns(assumed_scheduling_role, tag_key)
        )
        db_arns = [arn for arn in resource_arns if ":db:" in arn]
        cluster_arns = [arn for arn in resource_arns if ":cluster:" in arn]

        yield from cls.describe_rds_instances(assumed_scheduling_role, db_arns)
        yield from cls.describe_rds_clusters(assumed_scheduling_role, cluster_arns)

    @classmethod
    def describe_rds_resource(
        cls, assumed_scheduling_role: AssumedRole, resource_arn: str
    ) -> Optional[RdsRuntimeInfo]:
        arn_parts = resource_arn.split(":")
        if len(arn_parts) < 6:
            raise ValueError(f"Invalid RDS ARN format: {resource_arn}")

        is_cluster = ":cluster:" in resource_arn

        if is_cluster:
            return next(
                cls.describe_rds_clusters(assumed_scheduling_role, [resource_arn]), None
            )
        else:
            return next(
                cls.describe_rds_instances(assumed_scheduling_role, [resource_arn]),
                None,
            )

    @classmethod
    def describe_rds_instances(
        cls, assumed_scheduling_role: AssumedRole, db_arns: list[str]
    ) -> Iterator[RdsRuntimeInfo]:
        if not db_arns:
            return

        paginator: Final = assumed_scheduling_role.client("rds").get_paginator(
            "describe_db_instances"
        )
        # rds filter has max size of 50 arns
        for batch in batched(db_arns, 50):
            for page in paginator.paginate(
                Filters=[
                    {
                        "Name": "db-instance-id",
                        "Values": batch,
                    },
                ],
                PaginationConfig={"PageSize": 50},
            ):
                for instance in page["DBInstances"]:
                    yield RdsRuntimeInfo(
                        account=assumed_scheduling_role.account,
                        region=assumed_scheduling_role.region,
                        resource_id=instance["DBInstanceIdentifier"],
                        name=instance.get("DBName", instance["DBInstanceIdentifier"]),
                        tags={
                            tag["Key"]: tag["Value"]
                            for tag in instance.get("TagList", [])
                        },
                        current_state=instance["DBInstanceStatus"],
                        is_cluster=False,
                        engine_type=instance["Engine"],
                        arn=ARN(instance["DBInstanceArn"]),
                        preferred_maintenance_window=instance.get(
                            "PreferredMaintenanceWindow", ""
                        ),
                        current_size=instance["DBInstanceClass"],
                        ReadReplicaSourceDBInstanceIdentifier=instance.get(
                            "ReadReplicaSourceDBInstanceIdentifier"
                        ),
                        ReadReplicaDBInstanceIdentifiers=instance.get(
                            "ReadReplicaDBInstanceIdentifiers", []
                        ),
                    )

    @classmethod
    def describe_rds_clusters(
        cls, assumed_scheduling_role: AssumedRole, cluster_arns: list[str]
    ) -> Iterator[RdsRuntimeInfo]:
        if not cluster_arns:
            return

        paginator: Final = assumed_scheduling_role.client("rds").get_paginator(
            "describe_db_clusters"
        )
        for batch in batched(cluster_arns, 50):
            for page in paginator.paginate(
                Filters=[
                    {
                        "Name": "db-cluster-id",
                        "Values": batch,
                    },
                ],
                PaginationConfig={"PageSize": 50},
            ):
                for cluster in page["DBClusters"]:
                    yield RdsRuntimeInfo(
                        account=assumed_scheduling_role.account,
                        region=assumed_scheduling_role.region,
                        resource_id=cluster["DBClusterIdentifier"],
                        name=cluster.get(
                            "DatabaseName", cluster["DBClusterIdentifier"]
                        ),
                        tags={
                            tag["Key"]: tag["Value"]
                            for tag in cluster.get("TagList", [])
                        },
                        current_state=cluster["Status"],
                        is_cluster=True,
                        engine_type=cluster["Engine"],
                        arn=ARN(cluster["DBClusterArn"]),
                        preferred_maintenance_window=cluster.get(
                            "PreferredMaintenanceWindow", ""
                        ),
                        current_size=cluster.get("DBClusterInstanceClass", "cluster"),
                    )

    @property
    def service_name(self) -> str:
        return "rds"

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
                        name="RDS preferred Maintenance Window Period",  # NOSONAR - string duplication
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
                        name="RDS preferred Maintenance Window Period"  # NOSONAR - string duplication
                        + "-{}".format(start_day_string),
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
                        name="RDS preferred Maintenance Window Period"  # NOSONAR - string duplication
                        + "-{}".format(stop_day_string),
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
            name="RDS preferred Maintenance Window Schedule",
            periods=periods,
            timezone=ZoneInfo("UTC"),  # PreferredMaintenanceWindow field is in utc
            # https://docs.aws.amazon.com/cli/latest/reference/rds/describe-db-instances.html
            enforced=True,
        )

        return schedule

    def describe_managed_instances(self) -> Iterator[ManagedRdsInstance]:
        """Describe all RDS instances/clusters and return ManagedRdsInstance data"""
        logger.info(
            f"Fetching rds instances for account {self.scheduling_context.assumed_role.account} in region {self.scheduling_context.assumed_role.region}"
        )

        registry = self.scheduling_context.registry

        # Process instances and clusters
        for runtime_info in RdsService.describe_tagged_rds_resources(
            self.scheduling_context.assumed_role,
            self.scheduling_context.schedule_tag_key,
        ):
            registry_info = cast(
                Optional[RegisteredRdsInstance],
                registry.get(runtime_info.to_registry_key(), cache_only=True),
            )

            # create registry record if none exists
            if not registry_info:
                registry_info = RegisteredRdsInstance(
                    account=self.scheduling_context.assumed_role.account,
                    region=self.scheduling_context.assumed_role.region,
                    resource_id=runtime_info.resource_id,
                    arn=runtime_info.arn,
                    name=runtime_info.tags.get(
                        "Name", runtime_info.resource_id
                    ),  # Use Name tag or fall back to identifier
                    schedule=runtime_info.tags.get(
                        self.scheduling_context.schedule_tag_key, ""
                    ),
                    stored_state=InstanceState.UNKNOWN,
                )

            yield ManagedRdsInstance(
                registry_info=registry_info,
                runtime_info=runtime_info,
            )

    def _stop_instance_by_id(self, instance_id: str) -> None:

        def does_snapshot_exist(name: str) -> bool:
            try:
                resp = self.rds_client.describe_db_snapshots(
                    DBSnapshotIdentifier=name, SnapshotType="manual"
                )
                snapshot = resp.get("DBSnapshots", None)
                return snapshot is not None
            except Exception as ex:
                if type(ex).__name__ == "DBSnapshotNotFoundFault":
                    return False
                else:
                    raise ex

        args = {"DBInstanceIdentifier": instance_id}

        if self.env.enable_rds_snapshots:
            snapshot_name = "{}-stopped-{}".format(
                self.stack_name, instance_id
            ).replace(" ", "")
            args["DBSnapshotIdentifier"] = snapshot_name

            try:
                if does_snapshot_exist(snapshot_name):
                    self.rds_client.delete_db_snapshot(
                        DBSnapshotIdentifier=snapshot_name
                    )
                    logger.info(f"Deleted previous snapshot {snapshot_name}")
            except Exception:
                logger.error(f"Error deleting snapshot {snapshot_name}")

        self.rds_client.stop_db_instance(
            **args,
        )

    def _process_decision(  # NOSONAR - cognitive complexity
        self, decision: SchedulingDecision[ManagedRdsInstance]
    ) -> SchedulingResult[ManagedRdsInstance]:
        """Process a scheduling decision and return the result"""
        runtime_info = decision.instance.runtime_info

        match decision.action:
            case RequestedAction.START:
                if runtime_info.is_running:
                    return SchedulingResult.no_action_needed(
                        decision, "Instance is already running"
                    )

                # skip and try again next time by resetting stored_state to what it was previously
                if not runtime_info.is_in_schedulable_state:
                    return SchedulingResult.client_exception(
                        decision,
                        UnschedulableRDSResource(
                            "Instance is not in a schedulable state"
                        ),
                    )

                try:
                    if runtime_info.is_cluster:
                        self.rds_client.start_db_cluster(
                            DBClusterIdentifier=runtime_info.resource_id
                        )
                    else:
                        self.rds_client.start_db_instance(
                            DBInstanceIdentifier=runtime_info.resource_id
                        )
                    logger.debug(f"Started {runtime_info.arn}")
                    return SchedulingResult.success(decision)
                except Exception as ex:
                    logger.error(f"Error starting {runtime_info.arn}({str(ex)})")
                    return SchedulingResult.client_exception(decision, ex)

            case RequestedAction.STOP:
                if runtime_info.is_stopped:
                    return SchedulingResult.no_action_needed(
                        decision, "Instance is already stopped"
                    )

                if not runtime_info.is_in_schedulable_state:
                    # skip and try again next time by resetting stored_state to what it was previously
                    return SchedulingResult.client_exception(
                        decision,
                        UnschedulableRDSResource(
                            "Instance is not in a schedulable state"
                        ),
                    )

                try:
                    if runtime_info.is_cluster:
                        self.rds_client.stop_db_cluster(
                            DBClusterIdentifier=runtime_info.resource_id
                        )
                    else:
                        self._stop_instance_by_id(runtime_info.resource_id)
                    logger.debug(f"Stopped {runtime_info.arn}")
                    return SchedulingResult.success(decision)
                except Exception as ex:
                    logger.error(f"Error stopping {runtime_info.arn} ({str(ex)})")
                    return SchedulingResult.client_exception(decision, ex)

            case (
                RequestedAction.DO_NOTHING | RequestedAction.CONFIGURE
            ):  # configure has no meaning in this context
                return SchedulingResult.no_action_needed(decision)
            case _:
                assert_never(decision.action)
