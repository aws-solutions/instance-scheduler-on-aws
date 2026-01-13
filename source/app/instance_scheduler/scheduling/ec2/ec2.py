# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import json
from collections.abc import Iterator
from dataclasses import dataclass
from enum import IntEnum
from itertools import chain
from typing import TYPE_CHECKING, Final, List, Literal, Optional, Union, cast

from botocore.exceptions import ClientError
from instance_scheduler.configuration.instance_schedule import InstanceSchedule
from instance_scheduler.configuration.scheduling_context import (
    SchedulingContext,
)
from instance_scheduler.handler.environments.ice_retry_request_environment import (
    IceErrorRequestEnvironment,
)
from instance_scheduler.handler.environments.scheduling_request_environment import (
    SchedulingRequestEnvironment,
)
from instance_scheduler.maint_win.maintenance_window_context import (
    MaintenanceWindowContext,
)
from instance_scheduler.model import EC2SSMMaintenanceWindow
from instance_scheduler.model.maint_win import NoNextExecutionTimeError
from instance_scheduler.model.managed_instance import RegisteredEc2Instance, RegistryKey
from instance_scheduler.model.schedule_definition import ScheduleDefinition
from instance_scheduler.model.store.dynamo_mw_store import DynamoMWStore
from instance_scheduler.model.store.resource_registry import ResourceRegistry
from instance_scheduler.observability.error_codes import ErrorCode
from instance_scheduler.observability.powertools_logging import powertools_logger
from instance_scheduler.observability.tag_keys import ControlTagKey
from instance_scheduler.scheduling.ec2.ice_retry import IceRetryRequest
from instance_scheduler.scheduling.ec2.sqs import send_message_to_queue
from instance_scheduler.scheduling.scheduling_decision import (
    ManagedInstance,
    RequestedAction,
    RuntimeInfo,
    SchedulingDecision,
    make_scheduling_decision,
)
from instance_scheduler.scheduling.scheduling_result import (
    SchedulingAction,
    SchedulingResult,
)
from instance_scheduler.scheduling.states import InstanceState
from instance_scheduler.util.arn import ARN
from instance_scheduler.util.batch import bisect_retry
from instance_scheduler.util.session_manager import AssumedRole

if TYPE_CHECKING:
    from mypy_boto3_ec2.client import EC2Client
    from mypy_boto3_ec2.literals import InstanceStateNameType
    from mypy_boto3_ec2.type_defs import (
        DescribeInstancesResultTypeDef,
        FilterTypeDef,
        InstanceTypeDef,
        StopInstancesResultTypeDef,
    )
else:
    EC2Client = object
    InstanceStateNameType = object
    FilterTypeDef = object
    InstanceTypeDef = object
    TagTypeDef = object
    StopInstancesResultTypeDef = object
    DescribeInstancesResultTypeDef = object


class EC2StateCode(IntEnum):
    PENDING = 0x00
    RUNNING = 0x10
    SHUTTING_DOWN = 0x20
    TERMINATED = 0x30
    STOPPING = 0x40
    STOPPED = 0x50


def get_tags(instance: InstanceTypeDef) -> dict[str, str]:
    return {tag["Key"]: tag["Value"] for tag in instance.get("Tags", [])}


logger = powertools_logger()


@dataclass(kw_only=True)
class EC2RuntimeInfo(RuntimeInfo):
    """Runtime information from EC2 describe calls"""

    account: str
    region: str
    resource_id: str
    tags: dict[str, str]
    arn: ARN
    current_state: Literal[
        "running", "stopped", "pending", "shutting-down", "stopping", "terminated"
    ]
    current_size: str

    @classmethod
    def arn_for(cls, assumed_role: AssumedRole, resource_id: str) -> ARN:
        return ARN(
            f"arn:{assumed_role.partition}:ec2:{assumed_role.region}:{assumed_role.account}:instance/{resource_id}"
        )

    @property
    def is_in_schedulable_state(self) -> bool:
        return self.current_state in ["running", "stopped"]

    @property
    def is_running(self) -> bool:
        return self.current_state == "running"

    @property
    def is_stopped(self) -> bool:
        return self.current_state == "stopped"

    @property
    def size(self) -> str:
        return self.current_size

    @property
    def requested_instance_types(self) -> list[str]:
        preferred_instance_types = self.tags.get(
            ControlTagKey.PREFERRED_INSTANCE_TYPES.value
        )
        return (
            [t.strip() for t in preferred_instance_types.split(",")]
            if preferred_instance_types
            else []
        )

    def is_using_preferred_instance_type(self) -> bool:
        if not self.requested_instance_types:
            return True
        return self.current_size == self.requested_instance_types[0]


@dataclass(kw_only=True)
class ManagedEC2Instance(ManagedInstance):
    """Composite of registry info and runtime info"""

    registry_info: RegisteredEc2Instance
    runtime_info: EC2RuntimeInfo


class Ec2Service:
    scheduling_context: SchedulingContext
    mw_context: Optional[MaintenanceWindowContext] = None
    ice_retry_queue_url: Optional[str] = None

    def __init__(
        self,
        scheduling_context: SchedulingContext,
        env: Union[SchedulingRequestEnvironment, IceErrorRequestEnvironment],
    ) -> None:
        self.scheduling_context = scheduling_context
        self.ec2_client: Final[EC2Client] = scheduling_context.assumed_role.client(
            "ec2"
        )
        self.ice_retry_queue_url = env.ice_retry_queue_url

        if env.enable_ec2_ssm_maintenance_windows:
            self.mw_context = MaintenanceWindowContext(
                scheduling_context,
                mw_store=DynamoMWStore(env.maintenance_window_table_name),
            )

    def _send_ice_retry_request(
        self, decision: SchedulingDecision[ManagedEC2Instance]
    ) -> SchedulingResult[ManagedEC2Instance]:
        preferred_instance_types = (
            decision.instance.runtime_info.requested_instance_types
        )
        if self.ice_retry_queue_url is not None and len(preferred_instance_types) > 0:
            ice_retry_request = IceRetryRequest(
                account=self.scheduling_context.assumed_role.account,
                region=self.scheduling_context.assumed_role.region,
                instance_id=decision.instance.runtime_info.resource_id,
                preferred_instance_types=preferred_instance_types,
            )

            message_id = send_message_to_queue(
                queue_url=self.ice_retry_queue_url,
                delay_in_seconds=10,
                message_body=json.dumps(ice_retry_request),
            )
            logger.info(
                f"Sent ice retry request to queue with message ID: {message_id}"
            )
        return SchedulingResult.no_action_needed(decision, "Ice Retry Initiated")

    def schedule_target(self) -> Iterator[SchedulingResult[ManagedEC2Instance]]:
        registry = self.scheduling_context.registry
        registry.preload_cache(
            registry.find_by_scheduling_target(
                account=self.scheduling_context.assumed_role.account,
                region=self.scheduling_context.assumed_role.region,
                service="ec2",
            )
        )

        start_decisions: list[SchedulingDecision[ManagedEC2Instance]] = []
        stop_decisions: list[SchedulingDecision[ManagedEC2Instance]] = []
        hibernate_decisions: list[SchedulingDecision[ManagedEC2Instance]] = []
        do_nothing_decisions: list[SchedulingDecision[ManagedEC2Instance]] = []

        for managed_instance in self.describe_schedulable_instances():
            schedule = self.scheduling_context.schedule_store.find_by_name(
                managed_instance.registry_info.schedule,
                cache_only=True,  # cache should have been preloaded by scheduling request handler
            )

            if schedule is None:
                logger.info(
                    f"Schedule {managed_instance.registry_info.schedule} not found, skipping instance {managed_instance.registry_info.resource_id}"
                )
                yield SchedulingResult.shortcircuit_error(
                    resource=managed_instance,
                    error_code=ErrorCode.UNKNOWN_SCHEDULE,
                )
                continue

            decision = make_scheduling_decision(
                instance=managed_instance,
                schedule=schedule.to_instance_schedule(
                    self.scheduling_context.period_store
                ),
                current_dt=self.scheduling_context.current_dt,
                maintenance_windows=self._fetch_mw_schedules_for(schedule),
            )

            match decision.action:
                case RequestedAction.START:
                    start_decisions.append(decision)
                case RequestedAction.STOP:
                    if schedule.hibernate:
                        hibernate_decisions.append(decision)
                    else:
                        stop_decisions.append(decision)
                case RequestedAction.DO_NOTHING:
                    do_nothing_decisions.append(decision)
                case _:
                    logger.warning(
                        f"EC2 scheduling resulted in unrecognized decision type: {decision}"
                    )

        for scheduling_result in chain(
            self.start_instances(start_decisions),
            self.hibernate_instances(hibernate_decisions),
            self.stop_instances(stop_decisions),
            [SchedulingResult.no_action_needed(d) for d in do_nothing_decisions],
        ):
            if (
                scheduling_result.instance.registry_info
                != scheduling_result.updated_registry_info
            ):
                registry.put(scheduling_result.updated_registry_info, overwrite=True)

            yield scheduling_result

    @property
    def service_name(self) -> str:
        return "ec2"

    @classmethod
    def describe_tagged_instances(
        cls, assumed_scheduling_role: AssumedRole, tag_key: str
    ) -> Iterator[EC2RuntimeInfo]:
        paginator: Final = assumed_scheduling_role.client("ec2").get_paginator(
            "describe_instances"
        )
        # filter for all states that are not "terminated"
        states_in_scope: Final[list[InstanceStateNameType]] = [
            "pending",
            "running",
            "shutting-down",
            "stopped",
            "stopping",
        ]
        filters: Final[list[FilterTypeDef]] = [
            {"Name": "instance-state-name", "Values": states_in_scope},
            {"Name": "tag-key", "Values": [tag_key]},
        ]
        for page in paginator.paginate(Filters=filters):
            for reservation in page["Reservations"]:
                for instance in reservation["Instances"]:
                    if is_member_of_asg(instance):
                        logger.debug(
                            f'Omitted EC2 instance with ID {instance["InstanceId"]} because it is part of an AutoScaling Group'
                        )
                        continue

                    yield EC2RuntimeInfo(
                        account=assumed_scheduling_role.account,
                        region=assumed_scheduling_role.region,
                        resource_id=instance["InstanceId"],
                        tags=get_tags(instance),
                        current_state=instance["State"]["Name"],
                        current_size=instance["InstanceType"],
                        arn=EC2RuntimeInfo.arn_for(
                            assumed_scheduling_role, instance["InstanceId"]
                        ),
                    )

    @classmethod
    def describe_instance(
        cls, assumed_scheduling_role: AssumedRole, instance_id: str
    ) -> Optional[EC2RuntimeInfo]:
        """
        describe ec2 instance with the instance id
        """
        results: DescribeInstancesResultTypeDef = assumed_scheduling_role.client(
            "ec2"
        ).describe_instances(InstanceIds=[instance_id])
        for result in results["Reservations"]:
            for instance in result["Instances"]:
                logger.debug(
                    f"Found instance {instance['InstanceId']} in state {instance['State']['Name']}"
                )
                return EC2RuntimeInfo(
                    account=assumed_scheduling_role.account,
                    region=assumed_scheduling_role.region,
                    resource_id=instance["InstanceId"],
                    tags=get_tags(instance),
                    current_state=instance["State"]["Name"],
                    current_size=instance["InstanceType"],
                    arn=EC2RuntimeInfo.arn_for(
                        assumed_scheduling_role, instance["InstanceId"]
                    ),
                )
        return None

    @classmethod
    def fetch_or_create_registry_data(
        cls,
        ec2_instance: EC2RuntimeInfo,
        registry: ResourceRegistry,
        schedule_tag_key: str,
    ) -> RegisteredEc2Instance:
        """
        fetch or create registry data for the instance
        """
        registry_key = RegistryKey.from_arn(ec2_instance.arn)
        registry_data = cast(
            Optional[RegisteredEc2Instance], registry.get(registry_key)
        )
        if not registry_data:
            registry_data = RegisteredEc2Instance(
                account=ec2_instance.account,
                region=ec2_instance.region,
                resource_id=ec2_instance.resource_id,
                arn=ec2_instance.arn,
                name=ec2_instance.tags.get("Name", ""),
                schedule=ec2_instance.tags.get(schedule_tag_key, ""),
                stored_state=InstanceState.UNKNOWN,
            )
        return registry_data

    def describe_schedulable_instances(self) -> Iterator[ManagedEC2Instance]:
        """
        describe all EC2 instances in the target region and return `Instance` data for
        each instance that is schedulable

        an instance is schedulable if it satisfies:
        - in the `running` or `stopped` state
        - tagged with the schedule tag key

        also describe all maintenance windows, reconcile the DB with the service, and
        create `InstanceSchedule`s for each window
        """
        logger.info(
            f"Fetching ec2 instances for account {self.scheduling_context.assumed_role.account} in region {self.scheduling_context.assumed_role.region}"
        )

        for ec2_runtime_info in Ec2Service.describe_tagged_instances(
            self.scheduling_context.assumed_role,
            self.scheduling_context.schedule_tag_key,
        ):
            registry_info = Ec2Service.fetch_or_create_registry_data(
                ec2_runtime_info,
                self.scheduling_context.registry,
                self.scheduling_context.schedule_tag_key,
            )

            logger.debug(
                f'Selected EC2 instance with ID {registry_info.resource_id} in state "{ec2_runtime_info.current_state}"'
            )
            yield ManagedEC2Instance(
                runtime_info=ec2_runtime_info,
                registry_info=registry_info,
            )

    def _fetch_mw_schedules_for(
        self, schedule: ScheduleDefinition
    ) -> List[InstanceSchedule]:
        if not (self.mw_context and schedule.ssm_maintenance_window):
            return []

        maint_windows: list[EC2SSMMaintenanceWindow] = []
        for requested_mw_name in schedule.ssm_maintenance_window:
            maint_windows.extend(self.mw_context.find_by_name(requested_mw_name))

        schedules: list[InstanceSchedule] = []
        for mw in maint_windows:
            try:
                schedules.append(
                    mw.to_schedule(self.scheduling_context.scheduling_interval_minutes)
                )
            except NoNextExecutionTimeError:
                logger.warning(
                    f"Could not create schedule from maintenance window {mw.window_id}. Missing NextExecutionTime."
                )
        return schedules

    def stop_command(
        self,
        decisions: list[SchedulingDecision[ManagedEC2Instance]],
        hibernate: bool = False,
    ) -> StopInstancesResultTypeDef:
        instance_ids = [d.instance.runtime_info.resource_id for d in decisions]
        return self.ec2_client.stop_instances(
            InstanceIds=instance_ids, Hibernate=hibernate
        )

    def hibernate_instances(
        self,
        decisions: list[SchedulingDecision[ManagedEC2Instance]],
    ) -> Iterator[SchedulingResult[ManagedEC2Instance]]:
        # Filter out already stopped instances and yield no_action_needed for them
        decisions_to_hibernate = []
        for decision in decisions:
            if decision.instance.runtime_info.is_stopped:
                yield SchedulingResult.no_action_needed(
                    decision, "Instance is already stopped"
                )
            else:
                decisions_to_hibernate.append(decision)

        hibernate_responses: Final = bisect_retry(
            decisions_to_hibernate,
            lambda decision_list: self.stop_command(decision_list, hibernate=True),
        )

        if hibernate_responses.success_responses:
            successful_hibernations = [
                decision
                for response in hibernate_responses.success_responses
                for decision in response.successful_input
            ]

            for hibernated_decision in successful_hibernations:
                yield SchedulingResult.success(
                    hibernated_decision, SchedulingAction.HIBERNATE
                )

        retry_as_normal_stop = []
        for hibernate_failure in hibernate_responses.failure_responses:
            if (
                isinstance(hibernate_failure.error, ClientError)
                and hibernate_failure.error.response["Error"]["Code"]
                == "UnsupportedHibernationConfiguration"
            ):
                logger.warning(
                    f"EC2 instance with ID {hibernate_failure.failed_input.instance.runtime_info.resource_id} not configured for hibernation, attempting to stop"
                )
                retry_as_normal_stop.append(hibernate_failure.failed_input)

            else:
                logger.error(
                    f"Failed to stop EC2 instance with ID {hibernate_failure.failed_input.instance.runtime_info.resource_id}: {str(hibernate_failure.error)}"
                )

                yield SchedulingResult.client_exception(
                    hibernate_failure.failed_input,
                    error=hibernate_failure.error,
                )

        if retry_as_normal_stop:
            yield from self.stop_instances(retry_as_normal_stop)

    def stop_instances(
        self,
        decisions: list[SchedulingDecision[ManagedEC2Instance]],
    ) -> Iterator[SchedulingResult[ManagedEC2Instance]]:
        # Filter out already stopped instances and yield no_action_needed for them
        decisions_to_stop = []
        for decision in decisions:
            if decision.instance.runtime_info.is_stopped:
                yield SchedulingResult.no_action_needed(
                    decision, "Instance is already stopped"
                )
            else:
                decisions_to_stop.append(decision)

        stop_responses: Final = bisect_retry(
            decisions_to_stop,
            lambda decision_list: self.stop_command(decision_list, hibernate=False),
        )

        # Apply success tags and yield results
        if stop_responses.success_responses:
            successful_stops = [
                decision
                for response in stop_responses.success_responses
                for decision in response.successful_input
            ]

            for stopped_decision in successful_stops:
                yield SchedulingResult.success(stopped_decision)

        # Apply failure tags and return errors
        for stop_failure in stop_responses.failure_responses:
            logger.error(
                f"Failed to stop EC2 instance with ID {stop_failure.failed_input.instance.runtime_info.resource_id}: {str(stop_failure.error)}",
            )
            yield SchedulingResult.client_exception(stop_failure.failed_input)

    def start_instances(
        self, decisions: list[SchedulingDecision[ManagedEC2Instance]]
    ) -> Iterator[SchedulingResult[ManagedEC2Instance]]:
        # Filter out already running instances and yield no_action_needed for them
        decisions_to_start = []
        for decision in decisions:
            if decision.instance.runtime_info.is_running:
                yield SchedulingResult.no_action_needed(
                    decision, "Instance is already running"
                )
            elif not decision.instance.runtime_info.is_using_preferred_instance_type():
                yield self._send_ice_retry_request(decision)
            else:
                decisions_to_start.append(decision)

        responses: Final = bisect_retry(
            decisions_to_start,
            lambda decision_list: self.ec2_client.start_instances(
                InstanceIds=[
                    decision.instance.runtime_info.resource_id
                    for decision in decision_list
                ]
            ),
        )
        starting_instance_ids: Final[list[str]] = []

        for response in responses.success_responses:
            starting_instance_ids.extend(
                instance["InstanceId"]
                for instance in response.response["StartingInstances"]
            )

        # Yield success results
        # success event with not matching the preferred instance type should go through the ice retry lambda.
        for response in responses.success_responses:
            for started_decision in response.successful_input:
                yield SchedulingResult.success(started_decision)

        # Yield failure results
        for failure in responses.failure_responses:
            if (
                isinstance(failure.error, ClientError)
                and failure.error.response["Error"]["Code"]
                == "InsufficientInstanceCapacity"
            ):
                yield self._send_ice_retry_request(failure.failed_input)

            logger.error(
                f"Failed to start EC2 instance with ID {failure.failed_input.instance.runtime_info.resource_id}: {str(failure.error)}",
            )

            yield SchedulingResult.client_exception(
                failure.failed_input,
                error=failure.error,
            )


def is_member_of_asg(instance: InstanceTypeDef) -> bool:
    return any(
        True
        for _ in filter(
            lambda x: x["Key"] == "aws:autoscaling:groupName", instance["Tags"]
        )
    )
