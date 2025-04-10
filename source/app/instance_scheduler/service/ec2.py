# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from collections.abc import Iterator
from enum import IntEnum
from itertools import chain
from typing import TYPE_CHECKING, Final, List, Optional

from botocore.exceptions import ClientError

from instance_scheduler.configuration.instance_schedule import InstanceSchedule
from instance_scheduler.configuration.scheduling_context import (
    SchedulingContext,
    TagTemplate,
)
from instance_scheduler.handler.environments.scheduling_request_environment import (
    SchedulingRequestEnvironment,
)
from instance_scheduler.maint_win.maintenance_window_context import (
    MaintenanceWindowContext,
)
from instance_scheduler.model import EC2SSMMaintenanceWindow
from instance_scheduler.model.maint_win import NoNextExecutionTimeError
from instance_scheduler.model.store.dynamo_mw_store import DynamoMWStore
from instance_scheduler.schedulers.states import ScheduleState
from instance_scheduler.service import Service
from instance_scheduler.service.ec2_instance import EC2Instance
from instance_scheduler.util.batch import bisect_retry
from instance_scheduler.util.logger import Logger
from instance_scheduler.util.session_manager import AssumedRole

if TYPE_CHECKING:
    from mypy_boto3_ec2.client import EC2Client
    from mypy_boto3_ec2.literals import InstanceStateNameType
    from mypy_boto3_ec2.type_defs import FilterTypeDef, InstanceTypeDef, TagTypeDef
else:
    EC2Client = object
    InstanceStateNameType = object
    FilterTypeDef = object
    InstanceTypeDef = object
    TagTypeDef = object


class EC2StateCode(IntEnum):
    PENDING = 0x00
    RUNNING = 0x10
    SHUTTING_DOWN = 0x20
    TERMINATED = 0x30
    STOPPING = 0x40
    STOPPED = 0x50


def get_tags(instance: InstanceTypeDef) -> dict[str, str]:
    return {tag["Key"]: tag["Value"] for tag in instance.get("Tags", [])}


class Ec2Service(Service[EC2Instance]):

    mw_context: Optional[MaintenanceWindowContext] = None

    def __init__(
        self,
        assumed_scheduling_role: AssumedRole,
        logger: Logger,
        scheduling_context: SchedulingContext,
        env: SchedulingRequestEnvironment,
    ) -> None:
        self._spoke_session: Final = assumed_scheduling_role
        self._logger: Final = logger
        self._scheduling_context: Final = scheduling_context
        self._env: Final = env
        self._scheduler_tag_key: Final = self._env.schedule_tag_key

        self._ec2: Final[EC2Client] = self._spoke_session.client("ec2")

        if env.enable_ec2_ssm_maintenance_windows:
            self.mw_context = MaintenanceWindowContext(
                scheduling_context=self._scheduling_context,
                spoke_scheduler_role=assumed_scheduling_role,
                logger=self._logger,
                mw_store=DynamoMWStore(self._env.maintenance_window_table_name),
            )

    @property
    def service_name(self) -> str:
        return "ec2"

    def describe_tagged_instances(self) -> Iterator[EC2Instance]:
        """
        describe all EC2 instances in the target region and return `Instance` data for
        each instance that is schedulable

        an instance is schedulable if it satisfies:
        - in the `running` or `stopped` state
        - tagged with the schedule tag key

        also describe all maintenance windows, reconcile the DB with the service, and
        create `InstanceSchedule`s for each window
        """
        self._logger.info(
            f"Fetching ec2 instances for account {self._spoke_session.account} in region {self._spoke_session.region}"
        )

        paginator: Final = self._ec2.get_paginator("describe_instances")
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
            {"Name": "tag-key", "Values": [self._scheduler_tag_key]},
        ]
        for page in paginator.paginate(Filters=filters):
            for reservation in page["Reservations"]:
                for instance in reservation["Instances"]:
                    if is_member_of_asg(instance):
                        self._logger.info(
                            f'Omitted EC2 instance with ID {instance["InstanceId"]} because it is part of an AutoScaling Group'
                        )
                        continue

                    ec2_instance = self._select_instance_data(instance)

                    self._logger.info(
                        f'Selected EC2 instance with ID {ec2_instance.id} in state "{ec2_instance.current_state}"'
                    )
                    if ec2_instance.maintenance_windows:
                        self._logger.info(
                            f"EC2 instance ({ec2_instance.id}) selected with the following maintenance windows attached: "
                            f"{[mw.name for mw in ec2_instance.maintenance_windows]}"
                        )
                    yield ec2_instance

    def _select_instance_data(self, instance: InstanceTypeDef) -> EC2Instance:
        tags: Final = get_tags(instance)
        name: Final = tags.get("Name", "")
        instance_id: Final = instance["InstanceId"]
        schedule_name: Final = tags.get(self._scheduler_tag_key, "")
        schedule = self._scheduling_context.get_schedule(schedule_name)
        if schedule and schedule.use_maintenance_window:
            maint_windows = self._fetch_mw_schedules_for(schedule)
        else:
            maint_windows = []

        return EC2Instance(
            _id=instance_id,
            _schedule_name=schedule_name,
            _name=name,
            _current_state=instance["State"]["Name"],
            _instance_type=instance["InstanceType"],
            _tags=tags,
            _maintenance_windows=maint_windows,
        )

    def _fetch_mw_schedules_for(
        self, schedule: InstanceSchedule
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
                    mw.to_schedule(self._scheduling_context.scheduling_interval_minutes)
                )
            except NoNextExecutionTimeError:
                self._logger.warning(
                    f"Could not create schedule from maintenance window {mw.window_id}. Missing NextExecutionTime."
                )
        return schedules

    def resize_instance(self, instance: EC2Instance, instance_type: str) -> None:
        """
        change the instance type of the EC2 instance with ID in `instance` to
        `instance_type`
        """
        self._logger.info(
            f"Setting size for ec2 instance {instance.id} to {instance_type}"
        )

        try:
            self._ec2.modify_instance_attribute(
                InstanceId=instance.id, InstanceType={"Value": instance_type}
            )
        except Exception as ex:
            self._logger.error(f"Error resizing instance {instance.id}, ({str(ex)})")

    def stop_instances(
        self, instances_to_stop: list[EC2Instance]
    ) -> Iterator[tuple[str, ScheduleState]]:
        """
        stop EC2 instances with IDs in `instances_to_stop`

        hibernate instances tagged with schedules that have been configured for
        hibernate

        tag instances that were successfully stopped with the stop tag keys and values
        configured at a stack value, and remove start tag keys from the same instances
        """
        instance_ids_to_hibernate: Final[list[str]] = []
        instance_ids_to_stop: Final[list[str]] = []

        for instance in instances_to_stop:
            if instance.should_hibernate:
                # instances that are stopped for resizing cannot be hibernated
                if instance.resized:
                    self._logger.info(
                        f"EC2 instance with ID {instance.id} will not be hibernated because it must be stopped for resize"
                    )
                    instance_ids_to_stop.append(instance.id)
                else:
                    instance_ids_to_hibernate.append(instance.id)
            else:
                instance_ids_to_stop.append(instance.id)

        hibernate_responses: Final = bisect_retry(
            instance_ids_to_hibernate,
            lambda ids: self._ec2.stop_instances(InstanceIds=ids, Hibernate=True),
        )

        stopping_instance_ids: Final[list[str]] = []

        for response in hibernate_responses.failure_responses:
            if (
                isinstance(response.error, ClientError)
                and response.error.response["Error"]["Code"]
                == "UnsupportedHibernationConfiguration"
            ):
                self._logger.warning(
                    "EC2 instance with ID {} not configured for hibernation, attempting to stop",
                    response.failed_input,
                )
                instance_ids_to_stop.append(response.failed_input)
            else:
                self._logger.error(
                    "Failed to stop EC2 instance with ID {}: {}",
                    response.failed_input,
                    str(response.error),
                )

        stopping_instance_ids.extend(
            chain.from_iterable(
                (instance["InstanceId"] for instance in response["StoppingInstances"])
                for response in hibernate_responses.success_responses
            )
        )

        stop_responses: Final = bisect_retry(
            instance_ids_to_stop, lambda ids: self._ec2.stop_instances(InstanceIds=ids)
        )

        for response in stop_responses.failure_responses:
            self._logger.error(
                "Failed to stop EC2 instance with ID {}: {}",
                response.failed_input,
                str(response.error),
            )

        stopping_instance_ids.extend(
            chain.from_iterable(
                (instance["InstanceId"] for instance in response["StoppingInstances"])
                for response in stop_responses.success_responses
            )
        )

        self._tag_instances(
            stopping_instance_ids,
            tag_templates_to_add=self._scheduling_context.stopped_tags,
            tag_templates_to_remove=self._scheduling_context.started_tags,
        )

        yield from (
            (instance_id, ScheduleState.STOPPED)
            for instance_id in stopping_instance_ids
        )

    def start_instances(
        self, instances_to_start: list[EC2Instance]
    ) -> Iterator[tuple[EC2Instance, Exception]]:
        """
        start the EC2 instances with IDs in `instances_to_start`

        tag instances that were successfully started with the start tag keys and values
        configured at a stack value, and remove stop tag keys from the same instances

        @returns a tuple of instances that failed to start and the error message associated
        """
        responses: Final = bisect_retry(
            instances_to_start,
            lambda instances: self._ec2.start_instances(
                InstanceIds=[instance.id for instance in instances]
            ),
        )
        starting_instance_ids: Final[list[str]] = []

        for response in responses.success_responses:
            starting_instance_ids.extend(
                instance["InstanceId"] for instance in response["StartingInstances"]
            )

        self._tag_instances(
            starting_instance_ids,
            tag_templates_to_add=self._scheduling_context.started_tags,
            tag_templates_to_remove=self._scheduling_context.stopped_tags,
        )

        for failure in responses.failure_responses:
            self._logger.error(
                "Failed to start EC2 instance with ID {}: {}",
                failure.failed_input,
                str(failure.error),
            )

            yield failure.failed_input, failure.error

    def _tag_instances(
        self,
        instance_ids: list[str],
        *,
        tag_templates_to_add: list[TagTemplate],
        tag_templates_to_remove: list[TagTemplate],
    ) -> None:
        """
        add tags with keys and values in `tag_templates_to_add` to EC2 instances with
        IDs in `instance_ids`, and remove tag keys in `tag_templates_to_remove` from the
        same instances

        tag keys that appear in both lists are updated with the values in
        `tag_templates_to_add`
        """
        if not instance_ids:
            return

        tags_to_add: Final[list[TagTypeDef]] = [
            {"Key": tag["Key"], "Value": tag["Value"]} for tag in tag_templates_to_add
        ]
        tag_keys_to_add: Final = frozenset(tag["Key"] for tag in tags_to_add)
        tag_keys_to_remove: Final[list[TagTypeDef]] = [
            {"Key": tag["Key"]}
            for tag in tag_templates_to_remove
            if tag["Key"] not in tag_keys_to_add
        ]

        if tag_keys_to_remove:
            self._logger.info(
                "Removing tags with keys {} from instances with IDs {}",
                ", ".join(tag["Key"] for tag in tag_keys_to_remove),
                ", ".join(instance_ids),
            )
            try:
                self._ec2.delete_tags(Resources=instance_ids, Tags=tag_keys_to_remove)
            except Exception as err:
                self._logger.error(
                    "Error removing tags for instances with IDs {}: {}",
                    ", ".join(instance_ids),
                    str(err),
                )
        if tags_to_add:
            self._logger.info(
                "Adding tags {} to instances with IDs {}",
                str(tags_to_add),
                ", ".join(instance_ids),
            )
            try:
                self._ec2.create_tags(Resources=instance_ids, Tags=tags_to_add)
            except Exception as err:
                self._logger.error(
                    "Error adding tags for instances with IDs {}: {}",
                    ", ".join(instance_ids),
                    str(err),
                )


def is_member_of_asg(instance: InstanceTypeDef) -> bool:
    return any(
        True
        for _ in filter(
            lambda x: x["Key"] == "aws:autoscaling:groupName", instance["Tags"]
        )
    )
