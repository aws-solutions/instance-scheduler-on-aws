# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import time
from collections.abc import Iterator
from datetime import datetime
from typing import Any, Final, assert_never

from instance_scheduler.configuration.instance_schedule import InstanceSchedule
from instance_scheduler.configuration.scheduling_context import SchedulingContext
from instance_scheduler.handler.environments.scheduling_request_environment import (
    SchedulingRequestEnvironment,
)
from instance_scheduler.ops_metrics.metric_type.instance_count_metric import (
    InstanceCountMetric,
)
from instance_scheduler.ops_metrics.metric_type.scheduling_action_metric import (
    SchedulingActionMetric,
)
from instance_scheduler.ops_metrics.metrics import collect_metric
from instance_scheduler.ops_monitoring.cw_ops_insights import (
    CloudWatchOperationalInsights,
)
from instance_scheduler.ops_monitoring.instance_counts import (
    InstanceCountsAggregator,
    ServiceInstanceCounts,
)
from instance_scheduler.schedulers.instance_states import InstanceStates
from instance_scheduler.schedulers.scheduling_decision import (
    SchedulingAction,
    SchedulingDecision,
)
from instance_scheduler.schedulers.scheduling_result import SchedulingResult
from instance_scheduler.schedulers.states import InstanceState, ScheduleState
from instance_scheduler.service import Service
from instance_scheduler.service.abstract_instance import AbstractInstance
from instance_scheduler.util.logger import Logger


class InstanceScheduler:
    def __init__(
        self,
        service: Service[Any],
        scheduling_context: SchedulingContext,
        instance_states: InstanceStates,
        logger: Logger,
        env: SchedulingRequestEnvironment,
    ) -> None:
        self._service: Final = service
        self._scheduling_context: Final = scheduling_context
        self._instance_states: Final = instance_states
        self._logger: Final = logger
        self._env: Final = env

        self._metric_counts: InstanceCountsAggregator = InstanceCountsAggregator()

    def run(self) -> Any:
        execution_start = time.perf_counter()
        result = self._run_scheduler()
        execution_end = time.perf_counter()

        time_taken = execution_end - execution_start

        # op metrics
        collect_metric(
            InstanceCountMetric(
                service=self._scheduling_context.service,
                region=self._scheduling_context.region,
                num_schedules=len(result.instance_counts.by_schedule()),
                num_instances=sum(
                    count.total() for count in result.instance_counts.by_type().values()
                ),
            ),
            self._logger,
        )

        actions_taken = result.to_actions_taken(self._scheduling_context.service)
        if actions_taken:
            # only gather the metric if actions were actually taken
            collect_metric(
                SchedulingActionMetric(
                    duration_seconds=time_taken,
                    num_instances_scanned=sum(
                        count.total()
                        for count in result.instance_counts.by_type().values()
                    ),
                    num_unique_schedules=len(result.instance_counts.by_schedule()),
                    actions=result.to_actions_taken(self._scheduling_context.service),
                ),
                self._logger,
            )

        if self._env.enable_ops_monitoring:
            # dashboard metrics
            cw_metrics = CloudWatchOperationalInsights(self._env, self._logger)
            service_counts = ServiceInstanceCounts(
                {self._service.service_name: result.instance_counts}
            )

            cw_metrics.send_metrics_to_cloudwatch(
                service_counts, self._env.scheduler_frequency_minutes
            )

        return result.to_output_dict()

    def _run_scheduler(self) -> SchedulingResult:
        result = SchedulingResult()
        self._instance_states.load(
            account=self._scheduling_context.account_id,
            region=self._scheduling_context.region,
        )

        actions_to_take: dict[SchedulingAction, list[SchedulingDecision]] = {
            SchedulingAction.START: [],
            SchedulingAction.STOP: [],
        }

        for decision in self.make_scheduling_decisions(
            self._service.describe_tagged_instances(),
            self._instance_states,
            self._scheduling_context,
            result_object=result,
        ):
            self._logger.info(
                f"Scheduling decision for {decision.instance.display_str}: "
                f"\n  action: {decision.action} "
                f"\n  reason: {decision.reason}"
            )

            if decision.action is not SchedulingAction.DO_NOTHING:
                actions_to_take[decision.action].append(decision)

            if decision.new_state_table_state is not None:
                self._instance_states.set_instance_state(
                    decision.instance.id, decision.new_state_table_state
                )

        for failed_instance, err in self._handle_start_and_resize_actions(
            actions_to_take[SchedulingAction.START],
            result_object=result,
            logger=self._logger,
        ):
            self._logger.info(f"{failed_instance.display_str} failed to start: {err} ")
            self._instance_states.set_instance_state(
                failed_instance.id, InstanceState.START_FAILED
            )

        self._handle_stop_actions(
            actions_to_take[SchedulingAction.STOP],
            result_object=result,
            logger=self._logger,
        )

        self._instance_states.save()

        return result

    def make_scheduling_decisions(
        self,
        instances: Iterator[AbstractInstance],
        instance_states: InstanceStates,
        context: SchedulingContext,
        result_object: SchedulingResult,
    ) -> Iterator[SchedulingDecision]:
        for instance in instances:
            schedule = context.get_schedule(instance.schedule_name)

            if not schedule:
                self._logger.warning(
                    f"{instance.display_str} is tagged with an unknown schedule: {instance.schedule_name}"
                )
                yield SchedulingDecision(
                    instance=instance,
                    action=SchedulingAction.DO_NOTHING,
                    new_state_table_state=None,
                    reason=f"Unknown Schedule {instance.schedule_name}",
                )
                continue

            # do not count instances that are tagged with invalid schedules, but do count instances that are in
            # a non-schedulable state (which is typically transient)
            result_object.add_checked_instance(instance)

            if not instance.is_schedulable:
                yield SchedulingDecision(
                    instance=instance,
                    action=SchedulingAction.DO_NOTHING,
                    new_state_table_state=None,
                    reason=f"Current instance state ({instance.current_state}) is not schedulable",
                )
                continue

            dt = context.current_dt
            stored_state = instance_states.get_instance_state(instance.id)

            if schedule.hibernate:
                instance.should_hibernate = True

            yield self.make_scheduling_decision(instance, schedule, stored_state, dt)

    def make_scheduling_decision(  # NOSONAR -- splitting for cog-complexity would make this function harder to read
        self,
        instance: AbstractInstance,
        schedule: InstanceSchedule,
        stored_state: InstanceState,
        current_dt: datetime,
    ) -> SchedulingDecision:
        """
        :param instance: a schedulable instance
        :param schedule: the schedule the given instance is subject to
        :param stored_state: the state that was stored in the dynamodb states table
        :param current_dt: the current time
        :return: a decision on how to schedule the instance
        """

        mw_is_running, window_name = self._is_maintenance_window_running(
            instance, current_dt
        )
        if schedule.use_maintenance_window and mw_is_running:
            return SchedulingDecision(
                instance=instance,
                action=SchedulingAction.START,
                new_state_table_state=InstanceState.RUNNING,
                reason=f"In active maintenance window {window_name}",
            )

        # A Scheduling decision is based on 2 primary factors: the current state of the schedule (schedule_state),
        # and the instance state that was stored during the last scheduling execution (stored_state)
        # In general, the stored_state for a given instance will match the schedule_state that was present during
        # the last scheduling execution. This allows the scheduler to identify when a schedule state has changed
        # since the last execution and issue a start/stop command in response to this state transition (which typically
        # occurs at beginning/end of a running period)
        # This additional complexity allows customers to start/stop instances manually without InstanceScheduler
        # overriding the manual action until the next regular start/stop action. Additional states InstanceStates and
        # schedule flags can be used to modify this behavior to fit the customer needs (for example: enforced schedules
        # and the retain_running flag)
        schedule_state, new_desired_type, _ = schedule.get_desired_state(
            current_dt, logger=self._logger
        )
        match schedule_state:
            case ScheduleState.STOPPED:
                # stop_new_instances flag -- new instances that are running are optionally
                #                            not stopped to allow them to finish possible initialization
                if (
                    stored_state == InstanceState.UNKNOWN
                    and not schedule.stop_new_instances
                ):
                    return SchedulingDecision(
                        instance=instance,
                        action=SchedulingAction.DO_NOTHING,
                        new_state_table_state=InstanceState.STOPPED,
                        desired_size=new_desired_type,
                        reason="stop_new_instances is disabled",
                    )

                # enforced flag -- always take action if schedule is enforced
                if schedule.enforced:
                    return SchedulingDecision(
                        instance=instance,
                        action=SchedulingAction.STOP,
                        new_state_table_state=InstanceState.STOPPED,
                        desired_size=new_desired_type,
                        reason="enforced is enabled",
                    )

                # retain_running flag -- don't stop instances flagged with retain_running
                if (
                    stored_state == InstanceState.RETAIN_RUNNING
                    and schedule.retain_running
                ):
                    return SchedulingDecision(
                        instance=instance,
                        action=SchedulingAction.DO_NOTHING,
                        new_state_table_state=InstanceState.STOPPED,
                        desired_size=new_desired_type,
                        reason="Instance is in the RETAIN_RUNNING state",
                    )

                # normal scheduling behavior -- issue stop action if schedule state changed, otherwise do nothing
                if stored_state != schedule_state:  # type: ignore[comparison-overlap]
                    return SchedulingDecision(
                        instance=instance,
                        action=SchedulingAction.STOP,
                        new_state_table_state=InstanceState.STOPPED,
                        desired_size=new_desired_type,
                        reason=f"State transition from {stored_state} to {schedule_state}",
                    )
                else:
                    return SchedulingDecision(
                        instance=instance,
                        action=SchedulingAction.DO_NOTHING,
                        new_state_table_state=InstanceState.STOPPED,
                        desired_size=new_desired_type,
                        reason=f"No schedule state transition detected (prev state: {stored_state}, new state: {schedule_state})",
                    )

            case ScheduleState.RUNNING:
                # resize handling -- top priority
                if (
                    instance.is_resizable
                    and new_desired_type
                    and instance.is_running
                    and instance.instance_type != new_desired_type
                ):
                    # necessary to prevent the instance from hibernating
                    instance.resized = True
                    return SchedulingDecision(
                        instance=instance,
                        action=SchedulingAction.STOP,
                        new_state_table_state=InstanceState.STOPPED,
                        desired_size=new_desired_type,
                        reason=f"Current type {instance.instance_type} does not match desired type {new_desired_type}, "
                        f"stopping instance to allow for resizing to desired type",
                    )

                # enforced flag -- always take action if schedule is enforced
                if schedule.enforced:
                    return SchedulingDecision(
                        instance=instance,
                        action=SchedulingAction.START,
                        new_state_table_state=InstanceState.RUNNING,
                        desired_size=new_desired_type,
                        reason="enforced is enabled",
                    )

                # retain_running flag -- instance in stopped state is found to already be running
                if (
                    schedule.retain_running
                    and stored_state == InstanceState.STOPPED
                    and instance.is_running
                ):
                    return SchedulingDecision(
                        instance=instance,
                        action=SchedulingAction.DO_NOTHING,
                        new_state_table_state=InstanceState.RETAIN_RUNNING,
                        desired_size=new_desired_type,
                        reason="Instance appears to have already been started -- apply retain_running flag",
                    )

                # retain_running flag -- do not clear retain_running flag inside running period
                if stored_state == InstanceState.RETAIN_RUNNING:
                    return SchedulingDecision(
                        instance=instance,
                        action=SchedulingAction.DO_NOTHING,
                        new_state_table_state=InstanceState.RETAIN_RUNNING,
                        desired_size=new_desired_type,
                        reason="Instance in retain_running state -- do not remove the flag",
                    )

                if stored_state == InstanceState.START_FAILED:
                    return SchedulingDecision(
                        instance=instance,
                        action=SchedulingAction.START,
                        new_state_table_state=InstanceState.RUNNING,
                        desired_size=new_desired_type,
                        reason="Instance failed to start previously. Attempting to retry",
                    )

                # normal scheduling behavior -- issue start action if schedule state changed, otherwise do nothing
                if stored_state != schedule_state:  # type: ignore[comparison-overlap]
                    return SchedulingDecision(
                        instance=instance,
                        action=SchedulingAction.START,
                        new_state_table_state=InstanceState.RUNNING,
                        desired_size=new_desired_type,
                        reason=f"State transition from {stored_state} to {schedule_state}",
                    )
                else:
                    return SchedulingDecision(
                        instance=instance,
                        action=SchedulingAction.DO_NOTHING,
                        new_state_table_state=InstanceState.RUNNING,
                        desired_size=new_desired_type,
                        reason=f"No schedule state transition detected (prev state: {stored_state}, new state: {schedule_state})",
                    )

            case ScheduleState.ANY:
                # Any state -- never take action
                return SchedulingDecision(
                    instance=instance,
                    action=SchedulingAction.DO_NOTHING,
                    new_state_table_state=InstanceState.ANY,
                    desired_size=new_desired_type,
                    reason="Schedule is in the any state",
                )

            case _ as unreachable:
                assert_never(unreachable)

    def _handle_start_and_resize_actions(
        self,
        start_actions: list[SchedulingDecision],
        result_object: SchedulingResult,
        logger: Logger,
    ) -> Iterator[tuple[AbstractInstance, Exception]]:
        filtered_actions = []

        # filter out instances that are already running
        for action in start_actions:
            if action.action != SchedulingAction.START:
                raise ValueError("Non start action passed to handle_start_actions()")

            if action.instance.is_running:
                logger.info(
                    f"skipping start for {action.instance.id}: instance is already running"
                )
                continue  # skip instances that are already running

            # handle resizing
            if (
                action.desired_size
                and action.desired_size != action.instance.instance_type
            ):
                if not action.instance.is_resizable:
                    logger.warning(
                        "Instance {} with type {} does not support resizing",
                        action.instance.id,
                        action.instance.instance_type,
                    )
                else:
                    logger.info(
                        f"resizing {action.instance.id} from {action.instance.instance_type} to {action.desired_size}"
                    )

                    self._service.resize_instance(action.instance, action.desired_size)

                    result_object.add_resize_action(
                        action.instance, action.desired_size
                    )

                    # this mutation is necessary to correctly count started instances
                    action.instance._instance_type = action.desired_size

            filtered_actions.append(action)

        for action in filtered_actions:
            result_object.add_completed_action(action)

        for failed_instance, err in self._service.start_instances(
            [action.instance for action in filtered_actions]
        ):
            yield failed_instance, err

    def _handle_stop_actions(
        self,
        stop_actions: list[SchedulingDecision],
        result_object: SchedulingResult,
        logger: Logger,
    ) -> None:
        filtered_actions = []

        # filter out instances that are already stopped
        for action in stop_actions:
            if action.action != SchedulingAction.STOP:
                raise ValueError("Non stop action passed to handle_stop_actions()")
            if action.instance.is_stopped:  # skip instances that are already stopped
                logger.info(
                    f"skipping stop for {action.instance.id}: instance is not running"
                )
                continue
            filtered_actions.append(action)

        for action in filtered_actions:
            result_object.add_completed_action(action)

        list(
            self._service.stop_instances(
                [action.instance for action in filtered_actions]
            )
        )

    def _is_maintenance_window_running(
        self,
        instance: AbstractInstance,
        current_dt: datetime,
    ) -> tuple[bool, str | None]:
        """
        Checks maintenance window is enabled for a schedule and currently running on instance
        """
        if instance.maintenance_windows:
            for maintenance_window in instance.maintenance_windows:
                # get the desired state for the maintenance window at current UTC time
                (
                    inst_state,
                    _,
                    _,
                ) = maintenance_window.get_desired_state(
                    logger=self._logger,
                    dt=current_dt,
                )
                if inst_state == ScheduleState.RUNNING:
                    return True, maintenance_window.name

        return False, None
