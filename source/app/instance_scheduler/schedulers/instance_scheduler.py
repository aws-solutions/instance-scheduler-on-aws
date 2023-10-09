# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import time
from collections.abc import Iterator
from datetime import datetime, timezone
from typing import Any, Final, Optional, TypedDict

from typing_extensions import NotRequired

from instance_scheduler import ScheduleState
from instance_scheduler.configuration.instance_schedule import (
    Instance,
    InstanceSchedule,
)
from instance_scheduler.configuration.scheduling_context import SchedulingContext
from instance_scheduler.ops_metrics.metric_type.instance_count_metric import (
    InstanceCountMetric,
)
from instance_scheduler.ops_metrics.metric_type.scheduling_action_metric import (
    ActionTaken,
    SchedulingActionMetric,
)
from instance_scheduler.ops_metrics.metrics import collect_metric, should_collect_metric
from instance_scheduler.schedulers.instance_states import InstanceStates
from instance_scheduler.service import Service
from instance_scheduler.util.logger import Logger
from instance_scheduler.util.scheduler_metrics import SchedulerMetrics

ERR_SETTING_INSTANCE_TYPE = "Error changing instance type ({})"

INF_DESIRED_TYPE = ", desired type is {}"
INF_PROCESSING_ACCOUNT = "Running {} scheduler for account {}{} in region(s) {}"
INF_STARTING_INSTANCES = "Starting instances {} in region {}"
INF_STOPPED_INSTANCES = "Stopping instances {} in region {}"
INF_MAINTENANCE_WINDOW = (
    'Maintenance window "{}" used as running period found for instance {}'
)

INF_DO_NOT_STOP_RETAINED_INSTANCE = (
    "Instance {} was already running at start of period and schedule uses retain option, desired "
    "state set to {} but instance will not be stopped if it is still running."
)

WARN_SKIPPING_UNKNOWN_SCHEDULE = (
    'Skipping instance {} in region {} for account {}, schedule name "{}" is unknown'
)
WARN_RESIZE_NOT_SUPPORTED = "Instance {} with type {} does not support resizing"

DEBUG_STOPPED_REGION_INSTANCES = (
    "Listing instance {} in region {} to be stopped by scheduler"
)
DEBUG_INSTANCE_HEADER = "[ Instance {} ]"
DEBUG_NEW_INSTANCE = (
    'New instance "{}" will not be stopped until next scheduling period'
)
DEBUG_CURRENT_INSTANCE_STATE = (
    'Current state is {}, instance type is {}, schedule is "{}"'
)
DEBUG_SKIPPING_TERMINATED_INSTANCE = (
    'Skipping terminated instance "{}" in region {} for account {}'
)
DEBUG_STARTED_REGION_INSTANCES = (
    "Listing instance {} in region {} with instance type {} to be started by scheduler"
)
DEBUG_CURRENT_AND_DESIRED_STATE = (
    'Desired state for instance from schedule "{}" is {}, last desired state was {}, '
    "actual state is {}{} "
)
DEBUG_ENFORCED_STATE = "Using enforcement flag of schedule to set actual state of instance {} from {} to {}"
DEBUG_APPLY_RETAIN_RUNNING_STATE = (
    "Desired state is {} for instance {} which is already running and retain running period is "
    "used the schedule, desired state set to {} so it is not stopped automatically at the end of "
    "this running period"
)


class StartStopItem(TypedDict):
    schedule: Optional[str]


class ResizeItem(TypedDict):
    schedule: Optional[str]
    old: str
    new: str


StartStopItems = dict[str, list[dict[str, StartStopItem]]]
ResizeItems = dict[str, list[dict[str, ResizeItem]]]


class ProcessAccountResult(TypedDict):
    started: StartStopItems
    stopped: StartStopItems
    resized: NotRequired[ResizeItems]


class InstanceScheduler:
    def __init__(
        self,
        service: Service[Any],
        scheduling_context: SchedulingContext,
        instance_states: InstanceStates,
        account_id: str,
        role_arn: Optional[str],
        logger: Logger,
    ) -> None:
        self._service: Final = service
        self._scheduling_context: Final = scheduling_context
        self._instance_states: Final = instance_states
        self._account_id: Final = account_id
        self._role_arn: Final = role_arn
        self._logger: Final = logger

        self._region: Final = self._scheduling_context.region

        self._schedule_metrics: Final = SchedulerMetrics(datetime.now(timezone.utc))

        self._scheduler_start_list: list[Instance] = []
        self._scheduler_stop_list: list[Instance] = []
        self._schedule_resize_list: list[tuple[Instance, str]] = []

        self._usage_metrics: Final[dict[str, dict[str, Any]]] = {
            "Started": {},
            "Stopped": {},
            "Resized": {},
        }

    def _instance_display_str(self, inst_id: str, name: str) -> str:
        s = "{}:{}".format(self._service.service_name.upper(), inst_id)
        if name:
            s += " ({})".format(name)
        return s

    def _scheduled_instances_in_region(self) -> Iterator[Instance]:
        # use service strategy to get a list of instances that can be scheduled for that service
        for instance in self._service.get_schedulable_instances():
            instance["account"] = self._account_id
            instance["region"] = self._region
            instance["service"] = self._service.service_name
            instance["instance_str"] = self._instance_display_str(
                instance["id"], instance["name"]
            )
            yield instance

    def run(self) -> Any:
        execution_start = time.perf_counter()
        response, instances = self._process_account()
        execution_end = time.perf_counter()

        time_taken = execution_end - execution_start
        self._collect_op_metrics(instances=instances, time_taken=time_taken)

        return response

    def get_desired_state_and_type(
        self, schedule: InstanceSchedule, instance: Instance
    ) -> tuple[ScheduleState, Optional[str]]:
        # test if the instance has a maintenance window in which it must be running
        if (
            instance["maintenance_window"] is not None
            and schedule.use_maintenance_window is True
        ):
            self._logger.info(
                INF_MAINTENANCE_WINDOW,
                instance["maintenance_window"].name,
                instance["id"],
            )

            # get the desired start for the maintenance window at current UTC time
            (
                inst_state,
                inst_type,
                _,
            ) = instance["maintenance_window"].get_desired_state(
                instance,
                logger=self._logger,
                dt=datetime.now(
                    timezone.utc
                ),  # todo: using current time instead of schedule time?
            )

            # if we're in the maintenance window return running state
            if inst_state == InstanceSchedule.STATE_RUNNING:
                return inst_state, inst_type

        # based on the schedule get the desired state and instance type for this instance
        inst_state, inst_type, _ = schedule.get_desired_state(
            instance, logger=self._logger, dt=self._scheduling_context.current_dt
        )
        return inst_state, inst_type

    def _process_account(self) -> tuple[ProcessAccountResult, list[Instance]]:
        started_instances: StartStopItems = {}
        stopped_instances: StartStopItems = {}
        resized_instances: ResizeItems = {}

        self._logger.info(
            INF_PROCESSING_ACCOUNT,
            self._service.service_name.upper(),
            self._account_id,
            " using role " + (self._role_arn or ""),
            self._region,
        )

        state_loaded = False
        instances: list[Instance] = []

        self._scheduler_start_list = []
        self._scheduler_stop_list = []
        self._schedule_resize_list = []

        for instance in self._scheduled_instances_in_region():
            # delay loading instance state until first instance is returned
            if not state_loaded:
                self._instance_states.load(self._account_id, self._region)
                state_loaded = True

            instances.append(instance)

            # handle terminated instances
            if instance["is_terminated"]:
                self._logger.debug(
                    DEBUG_SKIPPING_TERMINATED_INSTANCE,
                    instance["instance_str"],
                    self._region,
                    instance["account"],
                )
                self._instance_states.delete_instance_state(instance["id"])
                continue

            # get the schedule for this instance
            instance_schedule = self._scheduling_context.get_schedule(
                instance["schedule_name"]
            )
            if not instance_schedule:
                self._logger.warning(
                    WARN_SKIPPING_UNKNOWN_SCHEDULE,
                    instance["instance_str"],
                    self._region,
                    instance["account"],
                    instance["schedule_name"],
                )
                continue

            self._logger.debug(DEBUG_INSTANCE_HEADER, instance["instance_str"])
            self._logger.debug(
                DEBUG_CURRENT_INSTANCE_STATE,
                instance["current_state"],
                instance["instancetype"],
                instance_schedule.name,
            )

            # based on the schedule get the desired state and instance type for this instance
            desired_state, desired_type = self.get_desired_state_and_type(
                instance_schedule, instance
            )

            # get the  previous desired instance state
            last_desired_state = self._instance_states.get_instance_state(
                instance["id"]
            )
            self._logger.debug(
                DEBUG_CURRENT_AND_DESIRED_STATE,
                instance_schedule.name,
                desired_state,
                last_desired_state,
                instance["current_state"],
                INF_DESIRED_TYPE.format(desired_type) if desired_type else "",
            )

            # last desired state None means this is the first time the instance is seen by the scheduler
            if last_desired_state is InstanceSchedule.STATE_UNKNOWN:
                # new instances that are running are optionally not stopped to allow them to finish possible initialization
                if (
                    instance["is_running"]
                    and desired_state == InstanceSchedule.STATE_STOPPED
                ):
                    if not instance_schedule.stop_new_instances:
                        self._instance_states.set_instance_state(
                            instance["id"], InstanceSchedule.STATE_STOPPED
                        )
                        self._logger.debug(DEBUG_NEW_INSTANCE, instance["instance_str"])
                        continue
                    self._process_new_desired_state(
                        instance,
                        desired_state,
                        desired_type,
                        last_desired_state,
                        instance_schedule.retain_running,
                    )
                else:
                    self._process_new_desired_state(
                        instance,
                        desired_state,
                        desired_type,
                        last_desired_state,
                        instance_schedule.retain_running,
                    )

            # existing instance

            # if enforced check the actual state with the desired state enforcing the schedule state
            elif instance_schedule.enforced:
                if (
                    instance["is_running"]
                    and desired_state == InstanceSchedule.STATE_STOPPED
                ) or (
                    not instance["is_running"]
                    and desired_state == InstanceSchedule.STATE_RUNNING
                ):
                    self._logger.debug(
                        DEBUG_ENFORCED_STATE,
                        instance["instance_str"],
                        InstanceSchedule.STATE_RUNNING
                        if instance["is_running"]
                        else InstanceSchedule.STATE_STOPPED,
                        desired_state,
                    )
                    self._process_new_desired_state(
                        instance,
                        desired_state,
                        desired_type,
                        last_desired_state,
                        instance_schedule.retain_running,
                    )
            # if not enforced then compare the schedule state with the actual state so state of manually started/stopped
            # instance it will honor that state
            elif last_desired_state != desired_state:
                self._process_new_desired_state(
                    instance,
                    desired_state,
                    desired_type,
                    last_desired_state,
                    instance_schedule.retain_running,
                )

            self._schedule_metrics.add_schedule_metrics(
                self._service.service_name, instance_schedule, instance
            )

        # process lists of instances that must be started or stopped
        self._start_and_stop_instances()

        # cleanup desired instance states and save
        self._instance_states.cleanup([i["id"] for i in instances])
        self._instance_states.save()

        # build output structure, hold started, stopped and resized instances per region
        if len(self._scheduler_start_list) > 0:
            started_instances[self._region] = [
                {i["id"]: {"schedule": i["schedule_name"]}}
                for i in self._scheduler_start_list
            ]
        if len(self._scheduler_stop_list):
            stopped_instances[self._region] = [
                {i["id"]: {"schedule": i["schedule_name"]}}
                for i in self._scheduler_stop_list
            ]
        if len(self._schedule_resize_list) > 0:
            resized_instances[self._region] = [
                {
                    i[0]["id"]: {
                        "schedule": i[0]["schedule_name"],
                        "old": i[0]["instancetype"],
                        "new": i[1],
                    }
                }
                for i in self._schedule_resize_list
            ]

        # put cloudwatch metrics
        if self._scheduling_context.use_metrics:
            self._schedule_metrics.put_schedule_metrics()

        # output data
        result: ProcessAccountResult = {
            "started": started_instances,
            "stopped": stopped_instances,
        }
        if self._service.allow_resize:
            result["resized"] = resized_instances
        return result, instances

    # handle new state of an instance
    def _process_new_desired_state(
        self,
        instance: Instance,
        desired_state: str,
        desired_type: Optional[str],
        last_desired_state: str,
        retain_running: Optional[bool],
    ) -> None:
        def need_and_can_resize() -> bool:
            if desired_type is not None and instance["instancetype"] != desired_type:
                if not instance["allow_resize"]:
                    self._logger.warning(
                        WARN_RESIZE_NOT_SUPPORTED,
                        instance["instance_str"],
                        instance["instancetype"],
                    )
                    return False
                else:
                    return True
            return False

        def resize_instance(inst: Instance, new_type: str) -> None:
            try:
                # adjust instance type before starting using the resize_instance method in the service_strategy
                self._service.resize_instance(instance, new_type)

                self._schedule_resize_list.append((inst, new_type))
            except Exception as ex:
                # if changing the instance type does fail do not add instance to start list so it is handled a next time
                self._logger.error(ERR_SETTING_INSTANCE_TYPE, str(ex))

        # last desired status was saved as retain-running
        if last_desired_state == InstanceSchedule.STATE_RETAIN_RUNNING:
            # don't change last desired state desired whilst in a running period
            if desired_state == InstanceSchedule.STATE_RUNNING:
                pass  # todo: should this be a return?

            # save last desired state as stopped (but do not stop) at the end of running period
            elif desired_state == InstanceSchedule.STATE_STOPPED:
                # safe new desired stopped state but keep running
                self._logger.debug(
                    INF_DO_NOT_STOP_RETAINED_INSTANCE,
                    instance["id"],
                    InstanceSchedule.STATE_STOPPED,
                )
                self._instance_states.set_instance_state(
                    instance["id"], InstanceSchedule.STATE_STOPPED
                )
            else:
                # just save new desired state
                self._instance_states.set_instance_state(instance["id"], desired_state)
        else:
            if desired_state == InstanceSchedule.STATE_RUNNING:
                if not instance["is_running"]:
                    inst_type = (
                        desired_type
                        if desired_type is not None
                        else instance["instancetype"]
                    )
                    self._logger.debug(
                        DEBUG_STARTED_REGION_INSTANCES,
                        instance["instance_str"],
                        instance["region"],
                        inst_type,
                    )

                    # for instances to be started test if resizing is required
                    if need_and_can_resize():
                        if not desired_type:
                            raise ValueError("Tried to resize with no desired type")
                        resize_instance(instance, desired_type)

                    # append instance to list of instances to start
                    self._scheduler_start_list.append(instance)

                # instance already running with desired state of running
                else:
                    # if retain running option is used in this save desired state as retained running.
                    if last_desired_state == InstanceSchedule.STATE_STOPPED:
                        if retain_running:
                            self._logger.debug(
                                DEBUG_APPLY_RETAIN_RUNNING_STATE,
                                desired_state,
                                instance["id"],
                                InstanceSchedule.STATE_RETAIN_RUNNING,
                            )
                            self._instance_states.set_instance_state(
                                instance["id"], InstanceSchedule.STATE_RETAIN_RUNNING
                            )
                        else:
                            # instance is running, set last desired state from stopped to started
                            self._instance_states.set_instance_state(
                                instance["id"], InstanceSchedule.STATE_RUNNING
                            )

                            # desired state is running but saved state already saves as retain running

            elif desired_state in [
                InstanceSchedule.STATE_STOPPED,
                InstanceSchedule.STATE_STOPPED_FOR_RESIZE,
            ]:
                if instance["is_running"]:
                    # instance needs to be stopped
                    self._logger.debug(
                        DEBUG_STOPPED_REGION_INSTANCES,
                        instance["instance_str"],
                        instance["region"],
                    )
                    # append instance to list of instances to start
                    if desired_state == InstanceSchedule.STATE_STOPPED_FOR_RESIZE:
                        instance["resized"] = True
                    self._scheduler_stop_list.append(instance)
                    # stopped instance with desired state of running but in retained state mode
                    # (manually stopped in running period and already running at start)
                else:
                    # just save new desired state
                    self._instance_states.set_instance_state(
                        instance["id"], InstanceSchedule.STATE_STOPPED
                    )

            else:
                self._instance_states.set_instance_state(instance["id"], desired_state)

    # start and stop listed instances
    def _start_and_stop_instances(self) -> None:
        if len(self._scheduler_start_list) > 0:
            self._logger.info(
                INF_STARTING_INSTANCES,
                ", ".join([i["instance_str"] for i in self._scheduler_start_list]),
                self._region,
            )

            for inst_id, state in self._service.start_instances(
                self._scheduler_start_list
            ):
                # set state based on returned state from start action
                self._instance_states.set_instance_state(inst_id, state)

        if len(self._scheduler_stop_list) > 0:
            self._logger.info(
                INF_STOPPED_INSTANCES,
                ", ".join([i["instance_str"] for i in self._scheduler_stop_list]),
                self._region,
            )
            for inst_id, state in self._service.stop_instances(
                self._scheduler_stop_list
            ):
                # set state based on start of stop action
                self._instance_states.set_instance_state(inst_id, state)

    # ------------------------METRICS--------------------------------#
    def _collect_op_metrics(self, instances: list[Instance], time_taken: float) -> None:
        if should_collect_metric(InstanceCountMetric, self._logger):
            self._collect_instance_count_metric(instances)

        if should_collect_metric(SchedulingActionMetric, self._logger):
            self._collect_scheduling_actions_metric(time_taken, instances)

    def _collect_instance_count_metric(self, instances: list[Instance]) -> None:
        collect_metric(
            InstanceCountMetric(
                service=self._scheduling_context.service,
                region=self._scheduling_context.region,
                num_instances=len(instances),
                num_schedules=self._count_unique_schedules(instances),
            ),
            logger=self._logger,
        )

    def _collect_scheduling_actions_metric(
        self, time_taken: float, instances: list[Instance]
    ) -> None:
        self._collect_usage_metrics()
        self._send_usage_metrics(time_taken, instances)

    @staticmethod
    def _count_unique_schedules(instances: list[Instance]) -> int:
        schedules = set()
        for instance in instances:
            schedules.add(instance.get("schedule_name"))

        return len(schedules)

    def _collect_usage_metrics(self) -> None:
        for i in self._scheduler_start_list:
            if i["id"] in [r[0]["id"] for r in self._schedule_resize_list]:
                instance_type = [
                    r[1] for r in self._schedule_resize_list if r[0]["id"] == i["id"]
                ][0]
            else:
                instance_type = i["instancetype"]
            if instance_type in self._usage_metrics["Started"]:
                self._usage_metrics["Started"][instance_type] += 1
            else:
                self._usage_metrics["Started"][instance_type] = 1

        for i in self._scheduler_stop_list:
            if i["instancetype"] in self._usage_metrics["Stopped"]:
                self._usage_metrics["Stopped"][i["instancetype"]] += 1
            else:
                self._usage_metrics["Stopped"][i["instancetype"]] = 1

        for resized_instance in self._schedule_resize_list:
            type_change = "{}-{}".format(
                resized_instance[0]["instancetype"], resized_instance[1]
            )
            if type_change in self._usage_metrics["Resized"]:
                self._usage_metrics["Resized"][type_change] += 1
            else:
                self._usage_metrics["Resized"][type_change] = 1

    def _send_usage_metrics(self, time_taken: float, instances: list[Instance]) -> None:
        for s in list(self._usage_metrics):
            if len(self._usage_metrics[s]) == 0:
                del self._usage_metrics[s]
        if len(self._usage_metrics) > 0:
            actions_taken = []
            for action in self._usage_metrics:
                for instance_type in self._usage_metrics.get(action, {}):
                    actions_taken.append(
                        ActionTaken(
                            instances=self._usage_metrics[action][instance_type],
                            action=action,
                            instanceType=instance_type,
                            service=self._service.service_name,
                        )
                    )

            collect_metric(
                SchedulingActionMetric(
                    duration_seconds=time_taken,
                    actions=actions_taken,
                    num_instances_scanned=len(instances),
                    num_unique_schedules=self._count_unique_schedules(instances),
                ),
                logger=self._logger,
            )
