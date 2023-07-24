# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from collections.abc import Iterator
from enum import IntEnum
from itertools import chain
from typing import TYPE_CHECKING, Final, Literal

from boto3 import Session

from instance_scheduler import ScheduleState
from instance_scheduler.configuration.instance_schedule import (
    Instance,
    InstanceSchedule,
)
from instance_scheduler.configuration.scheduling_context import TagTemplate
from instance_scheduler.maint_win import EC2SSMMaintenanceWindows
from instance_scheduler.service import Service, ServiceArgs
from instance_scheduler.util import get_boto_config
from instance_scheduler.util.app_env import get_app_env
from instance_scheduler.util.batch import FailureResponse, bisect_retry

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


class Ec2Service(Service[Instance]):
    def __init__(self, args: ServiceArgs) -> None:
        Service.__init__(self, args)

        self._spoke_session: Final = args["session"]
        self._spoke_account_id: Final = args["account_id"]
        self._logger: Final = args["logger"]
        self._scheduling_context: Final = args["scheduling_context"]

        self._spoke_region: Final = self._spoke_session.region_name
        self._scheduler_tag_key: Final = self._scheduling_context.tag_name

        self._ec2: Final[EC2Client] = self._spoke_session.client(
            "ec2", config=get_boto_config()
        )

        self._maintenance_window_schedules: dict[
            str, InstanceSchedule | Literal["NOT-FOUND"]
        ] = {}

        app_env: Final = get_app_env()

        self._maintenance_windows = EC2SSMMaintenanceWindows(
            hub_session=Session(),
            spoke_account_id=self._spoke_account_id,
            spoke_session=self._spoke_session,
            table_name=app_env.maintenance_window_table_name,
            scheduler_interval=app_env.scheduler_frequency_minutes,
            logger=self._logger,
        )

    @property
    def service_name(self) -> str:
        return "ec2"

    @property
    def allow_resize(self) -> bool:
        return True

    def get_schedulable_instances(self) -> list[Instance]:
        """
        describe all EC2 instances in the target region and return `Instance` data for
        each instance that is schedulable

        an instance is schedulable if it satisifes:
        - in the `running` or `stopped` state
        - tagged with the schedule tag key

        also describe all maintenance windows, reconcile the DB with the service, and
        create `InstanceSchedule`s for each window
        """
        schedules_with_hibernation: Final = frozenset(
            s.name for s in self._scheduling_context.schedules.values() if s.hibernate
        )

        self._logger.info(
            "Enable SSM Maintenance window is set to {}",
            self._scheduling_context.enable_ssm_maintenance_windows,
        )
        if self._scheduling_context.enable_ssm_maintenance_windows:
            # calling the get maintenance window for this account and region.
            self._logger.info(
                "load the ssm maintenance windows for account {}, and region {}",
                self._spoke_account_id,
                self._spoke_region,
            )
            self._maintenance_window_schedules = (
                self._maintenance_windows.ssm_maintenance_windows(
                    self._spoke_session, self._spoke_account_id, self._spoke_region
                )
            )
            self._logger.info("finish loading the ssm maintenance windows")

        self._logger.info(
            "Fetching ec2 instances for account {} in region {}",
            self._spoke_account_id,
            self._spoke_region,
        )

        paginator: Final = self._ec2.get_paginator("describe_instances")
        schedulable_states: Final[list[InstanceStateNameType]] = ["running", "stopped"]
        filters: Final[list[FilterTypeDef]] = [
            {"Name": "instance-state-name", "Values": schedulable_states},
            {"Name": "tag-key", "Values": [self._scheduler_tag_key]},
        ]
        instances: Final[list[Instance]] = []
        for page in paginator.paginate(Filters=filters):
            for reservation in page["Reservations"]:
                for instance in reservation["Instances"]:
                    instance_data = self._select_instance_data(
                        instance, schedules_with_hibernation
                    )
                    instances.append(instance_data)

                    self._logger.info(
                        'Selected EC2 instance with ID {} in state "{}"',
                        instance_data["id"],
                        instance_data["state_name"],
                    )

        self._logger.info(
            "Quantity of EC2 instances in schedulable states: {}",
            len(instances),
        )

        return instances

    def _select_instance_data(
        self, instance: InstanceTypeDef, schedules_with_hibernation: frozenset[str]
    ) -> Instance:
        tags: Final = get_tags(instance)
        name: Final = tags.get("Name", "")
        instance_id: Final = instance["InstanceId"]
        state_code: Final = instance["State"]["Code"] & 0xFF
        is_running: Final = state_code == EC2StateCode.RUNNING
        is_terminated: Final = state_code == EC2StateCode.TERMINATED
        schedule_name: Final = tags.get(self._scheduler_tag_key)

        maintenance_window_schedule: InstanceSchedule | Literal[
            "NOT-FOUND"
        ] | None = None
        schedule = None

        if schedule_name is not None:
            schedule = self._scheduling_context.schedules.get(schedule_name)
        if (
            schedule is not None
            and schedule.use_maintenance_window
            and schedule.ssm_maintenance_window
        ):
            maintenance_window_schedule = self._maintenance_window_schedules.get(
                schedule.ssm_maintenance_window, None
            )
            if maintenance_window_schedule is None:
                self._logger.error(
                    (
                        "SSM maintenance window {} used in schedule {} not found or "
                        "disabled"
                    ),
                    schedule.ssm_maintenance_window,
                    schedule.name,
                )
                self._maintenance_window_schedules[
                    schedule.ssm_maintenance_window
                ] = "NOT-FOUND"
        if maintenance_window_schedule == "NOT-FOUND":
            maintenance_window_schedule = None

        return Instance(
            id=instance_id,
            schedule_name=schedule_name,
            hibernate=schedule_name in schedules_with_hibernation,
            name=name,
            state=state_code,
            state_name=instance["State"]["Name"],
            allow_resize=self.allow_resize,
            resized=False,
            is_running=is_running,
            is_terminated=is_terminated,
            current_state="running" if is_running else "stopped",
            instancetype=instance["InstanceType"],
            tags=tags,
            maintenance_window=maintenance_window_schedule,
        )

    def resize_instance(self, instance: Instance, instance_type: str) -> None:
        """
        change the instance type of the EC2 instance with ID in `instance` to
        `instance_type`
        """
        self._logger.info(
            "Setting size for ec2 instance {} to {}", instance["id"], instance_type
        )

        try:
            self._ec2.modify_instance_attribute(
                InstanceId=instance["id"], InstanceType={"Value": instance_type}
            )
        except Exception as ex:
            self._logger.error(
                "Error resizing instance {}, ({})", instance["id"], str(ex)
            )

    def stop_instances(
        self, instances_to_stop: list[Instance]
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
            # instances that are stopped for resizing cannot be hibernated
            if instance["hibernate"] and instance["resized"]:
                self._logger.info(
                    (
                        "EC2 instance with ID {} will not be hibernated because it "
                        "must be stopped for resize"
                    ),
                    instance["id"],
                )

            if instance["hibernate"] and not instance["resized"]:
                instance_ids_to_hibernate.append(instance["id"])
            else:
                instance_ids_to_stop.append(instance["id"])

        hibernate_responses = bisect_retry(
            instance_ids_to_hibernate,
            lambda ids: self._ec2.stop_instances(InstanceIds=ids, Hibernate=True),
        )

        stop_responses = bisect_retry(
            instance_ids_to_stop, lambda ids: self._ec2.stop_instances(InstanceIds=ids)
        )

        stopping_instance_ids: Final[list[str]] = []

        for response in chain(hibernate_responses, stop_responses):
            if isinstance(response, FailureResponse):
                self._logger.error(
                    "Failed to stop EC2 instance with ID {}: {}",
                    response.failed_input,
                    str(response.error),
                )
            else:
                stopping_instance_ids.extend(
                    instance["InstanceId"] for instance in response["StoppingInstances"]
                )

        self._tag_instances(
            stopping_instance_ids,
            tag_templates_to_add=self._scheduling_context.stopped_tags,
            tag_templates_to_remove=self._scheduling_context.started_tags,
        )

        yield from ((instance_id, "stopped") for instance_id in stopping_instance_ids)

    def start_instances(
        self, instances_to_start: list[Instance]
    ) -> Iterator[tuple[str, ScheduleState]]:
        """
        start the EC2 instances with IDs in `instances_to_start`

        tag instances that were successfully started with the start tag keys and values
        configured at a stack value, and remove stop tag keys from the same instances
        """
        instance_ids = [instance["id"] for instance in instances_to_start]
        responses: Final = bisect_retry(
            instance_ids, lambda ids: self._ec2.start_instances(InstanceIds=ids)
        )
        starting_instance_ids: Final[list[str]] = []
        for response in responses:
            if isinstance(response, FailureResponse):
                self._logger.error(
                    "Failed to start EC2 instance with ID {}: {}",
                    response.failed_input,
                    str(response.error),
                )
            else:
                starting_instance_ids.extend(
                    instance["InstanceId"] for instance in response["StartingInstances"]
                )

        self._tag_instances(
            starting_instance_ids,
            tag_templates_to_add=self._scheduling_context.started_tags,
            tag_templates_to_remove=self._scheduling_context.stopped_tags,
        )

        yield from ((instance_id, "running") for instance_id in starting_instance_ids)

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
