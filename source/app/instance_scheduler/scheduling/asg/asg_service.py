# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from collections.abc import Iterator
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Final, Optional, Tuple, cast
from zoneinfo import ZoneInfo

from aws_lambda_powertools.logging import Logger
from instance_scheduler.configuration.scheduling_context import SchedulingContext
from instance_scheduler.configuration.time_utils import parse_time_str
from instance_scheduler.cron.asg import (
    to_asg_expr_monthdays,
    to_asg_expr_months,
    to_asg_expr_weekdays,
)
from instance_scheduler.cron.parser import (
    parse_monthdays_expr,
    parse_months_expr,
    parse_weekdays_expr,
)
from instance_scheduler.model.managed_instance import (
    AsgConfiguration,
    RegisteredAsgInstance,
    RegistryKey,
)
from instance_scheduler.model.period_definition import PeriodDefinition
from instance_scheduler.model.schedule_definition import ScheduleDefinition
from instance_scheduler.model.store.period_definition_store import PeriodDefinitionStore
from instance_scheduler.observability.error_codes import ErrorCode
from instance_scheduler.scheduling.asg.asg_runtime_info import (
    MDM_TAG_KEY,
    AsgRuntimeInfo,
)
from instance_scheduler.scheduling.asg.asg_size import AsgSize
from instance_scheduler.scheduling.scheduling_decision import (
    ManagedInstance,
    RequestedAction,
    SchedulingDecision,
)
from instance_scheduler.scheduling.scheduling_result import (
    SchedulingAction,
    SchedulingResult,
)
from instance_scheduler.scheduling.states import InstanceState
from instance_scheduler.util.session_manager import AssumedRole

if TYPE_CHECKING:
    from mypy_boto3_autoscaling.client import AutoScalingClient
    from mypy_boto3_autoscaling.type_defs import (
        ScheduledUpdateGroupActionRequestTypeDef,
        ScheduledUpdateGroupActionTypeDef,
    )
else:
    AutoScalingClient = object
    ScheduledUpdateGroupActionRequestTypeDef = object
    ScheduledUpdateGroupActionTypeDef = object
    TagDescriptionTypeDef = object
    AutoScalingGroupTypeDef = object
    TagTypeDef = object

logger: Final = Logger(log_uncaught_exceptions=True, use_rfc3339=True)


@dataclass
class ManagedAsgInstance(ManagedInstance):
    registry_info: RegisteredAsgInstance
    runtime_info: AsgRuntimeInfo


class AsgTagValidationError(Exception):
    pass


class BatchDeleteScheduledActionsError(Exception):
    pass


class BatchPutScheduledActionsError(Exception):
    pass


class AsgService:
    client: Final[AutoScalingClient]

    def __init__(
        self,
        context: SchedulingContext,
    ) -> None:
        self.context = context
        self.client = context.assumed_role.client("autoscaling")

    def schedule_target(self) -> Iterator[SchedulingResult[ManagedAsgInstance]]:
        self.context.registry.preload_cache(
            self.context.registry.find_by_scheduling_target(
                account=self.context.assumed_role.account,
                region=self.context.assumed_role.region,
                service="autoscaling",
            )
        )

        for asg_runtime_info in AsgService.describe_tagged_asgs(
            self.context.assumed_role, self.context.schedule_tag_key
        ):
            registry_info = cast(
                Optional[RegisteredAsgInstance],
                self.context.registry.get(RegistryKey.from_arn(asg_runtime_info.arn)),
            )
            if not registry_info:
                logger.info(
                    f"{asg_runtime_info.arn} is not registered for scheduling. skipping..."
                )
                continue

            result = self.schedule_asg(
                ManagedAsgInstance(
                    runtime_info=asg_runtime_info, registry_info=registry_info
                )
            )

            if result.instance.registry_info != result.updated_registry_info:
                self.context.registry.put(result.updated_registry_info, overwrite=True)

            yield result

    @classmethod
    def describe_tagged_asgs(
        cls, assumed_scheduling_role: AssumedRole, tag_key: str
    ) -> Iterator[AsgRuntimeInfo]:
        paginator: Final = assumed_scheduling_role.client("autoscaling").get_paginator(
            "describe_auto_scaling_groups"
        )
        for page in paginator.paginate(
            Filters=[{"Name": "tag-key", "Values": [tag_key]}]
        ):
            for group in page["AutoScalingGroups"]:
                yield AsgRuntimeInfo(group=group)

    @classmethod
    def describe_asgs(
        cls, scheduling_role: AssumedRole, asg_names: list[str]
    ) -> Iterator[AsgRuntimeInfo]:
        client = scheduling_role.client("autoscaling")
        response = client.describe_auto_scaling_groups(AutoScalingGroupNames=asg_names)
        for group in response["AutoScalingGroups"]:
            yield AsgRuntimeInfo(group=group)

    @classmethod
    def is_compatibile_schedule(
        cls, schedule: ScheduleDefinition, period_store: PeriodDefinitionStore
    ) -> Tuple[bool, str]:
        """returns: [isCompatible, reason]"""
        try:
            schedule_to_actions(schedule, period_store, AsgSize(1, 1, 1), "test-build")
            return True, ""
        except NotImplementedError as e:
            return False, str(e)

    def schedule_asg(
        self,
        group: ManagedAsgInstance,
    ) -> SchedulingResult[ManagedAsgInstance]:
        runtime_info = group.runtime_info
        mdm_tag = runtime_info.tags.get(MDM_TAG_KEY)

        # Create MDM tag if missing and determine requested size
        if mdm_tag:
            requested_size = AsgSize.from_mdm_str(mdm_tag)
        else:
            requested_size = runtime_info.current_asg_size
            self.write_mdm_tag(runtime_info, requested_size)

        schedule = self.context.schedule_store.find_by_name(
            group.registry_info.schedule
        )
        if not schedule:
            return SchedulingResult.shortcircuit_error(
                resource=group, error_code=ErrorCode.UNKNOWN_SCHEDULE
            )

        requested_schedule_hash = schedule.to_hash(self.context.period_store)

        if group.registry_info.last_configured:
            # trigger an update if the last configuration will become invalid within the next 24 hours
            valid_until = datetime.fromisoformat(
                group.registry_info.last_configured.valid_until
            ) - timedelta(days=1)
            configured_size = group.registry_info.last_configured.asg_size
            configured_schedule_hash = group.registry_info.last_configured.schedule_hash

            if (
                valid_until > self.context.current_dt
                and configured_size == requested_size
                and configured_schedule_hash == requested_schedule_hash
            ):

                return SchedulingResult.no_action_needed(
                    SchedulingDecision(
                        instance=group,
                        action=RequestedAction.DO_NOTHING,
                        new_stored_state=InstanceState.CONFIGURED,
                        reason="Configuration still valid",
                    ),
                )

        try:
            valid_until = self.configure_scheduled_scaling_rules(
                asg=group.runtime_info,
                schedule=schedule,
                period_store=self.context.period_store,
                running_state=requested_size,
            )

            new_config: Optional[AsgConfiguration] = AsgConfiguration(
                last_updated=datetime.now(timezone.utc).isoformat(),
                min=requested_size.min_size,
                desired=requested_size.desired_size,
                max=requested_size.max_size,
                schedule_hash=requested_schedule_hash,
                valid_until=valid_until.isoformat(),
            )

            return SchedulingResult.success(
                SchedulingDecision(
                    instance=group,
                    action=RequestedAction.CONFIGURE,
                    new_stored_state=InstanceState.CONFIGURED,
                    reason="current configuration is no longer valid",
                ),
                SchedulingAction.CONFIGURE,
                updated_registry_info=replace(
                    group.registry_info,
                    stored_state=InstanceState.CONFIGURED,
                    last_configured=new_config,
                ),
            )

        except Exception as e:
            logger.error(
                f"Failed to schedule {group.runtime_info.arn}: {e}", exc_info=True
            )
            return SchedulingResult.client_exception(
                SchedulingDecision(
                    instance=group,
                    action=RequestedAction.CONFIGURE,
                    new_stored_state=InstanceState.CONFIGURED,  # the state that would have been stored, the helper will replace this with an error
                    reason=f"Configuration error: {str(e)}",
                ),
            )

    def write_mdm_tag(
        self,
        group: AsgRuntimeInfo,
        requested_size: AsgSize,
    ) -> None:
        """
        Write the MDM tag to the ASG
        """
        asg_name = group.group["AutoScalingGroupName"]

        self.client.create_or_update_tags(
            Tags=[
                {
                    "ResourceId": asg_name,
                    "ResourceType": "auto-scaling-group",
                    "Key": MDM_TAG_KEY,
                    "Value": requested_size.to_mdm_str(),
                    "PropagateAtLaunch": False,
                }
            ]
        )

    def _describe_scheduled_actions(
        self, auto_scaling_group_name: str
    ) -> Iterator[ScheduledUpdateGroupActionTypeDef]:
        """
        Generator to get existing scheduled actions from an auto scaling group.
        It returns existing scheduled update group actions on an auto scaling group.

        :param auto_scaling_group_name: auto scaling group name
        :return: a scheduled action
        """

        paginator: Final = self.client.get_paginator("describe_scheduled_actions")

        for page in paginator.paginate(AutoScalingGroupName=auto_scaling_group_name):
            for action in page["ScheduledUpdateGroupActions"]:
                yield action

    def delete_existing_scheduled_actions(self, asg_name: str) -> Tuple[
        list[ScheduledUpdateGroupActionRequestTypeDef],
        Optional[BatchDeleteScheduledActionsError],
    ]:
        """
        :returns [original list of actions before deletion attempt, any exception that occured]
        """
        actions_to_delete: Final[list[ScheduledUpdateGroupActionRequestTypeDef]] = cast(
            list[ScheduledUpdateGroupActionRequestTypeDef],
            self.get_existing_scheduled_scaling_rules(asg_name=asg_name),
        )

        try:
            self._batch_delete_scheduled_action(
                scheduled_actions=actions_to_delete,
                auto_scaling_group_name=asg_name,
            )
            return actions_to_delete, None
        except BatchDeleteScheduledActionsError as e:
            return actions_to_delete, e

    def _batch_delete_scheduled_action(
        self,
        scheduled_actions: (
            list[ScheduledUpdateGroupActionTypeDef]
            | list[ScheduledUpdateGroupActionRequestTypeDef]
        ),
        auto_scaling_group_name: str,
    ) -> None:
        """
        Batch delete scheduled actions configured by the solution.
        When any failed scheduled actions happen, raise `BatchDeleteScheduledActionError`.

        :param scheduled_actions: solution configured scheduled actions
        :param auto_scaling_group_name: auto scaling group name
        """
        if len(scheduled_actions) > 0:
            delete_response = self.client.batch_delete_scheduled_action(
                AutoScalingGroupName=auto_scaling_group_name,
                ScheduledActionNames=[
                    action["ScheduledActionName"] for action in scheduled_actions
                ],
            )

            # deleting individual actions may fail, need to check response
            if len(delete_response["FailedScheduledActions"]) > 0:
                raise BatchDeleteScheduledActionsError(
                    f'Failed to delete some actions: {delete_response["FailedScheduledActions"]}'
                )

    def _batch_put_scheduled_update_group_action(
        self,
        scheduled_update_group_actions: list[ScheduledUpdateGroupActionRequestTypeDef],
        auto_scaling_group_name: str,
    ) -> None:
        """
        Batch put scheduled actions configured by the solution.

        :param scheduled_update_group_actions: solution configured scheduled actions
        :param auto_scaling_group_name: auto scaling group name
        """

        if len(scheduled_update_group_actions) > 0:
            put_response = self.client.batch_put_scheduled_update_group_action(
                AutoScalingGroupName=auto_scaling_group_name,
                ScheduledUpdateGroupActions=scheduled_update_group_actions,
            )

            # creating individual actions may fail, need to check response
            if len(put_response["FailedScheduledUpdateGroupActions"]) > 0:
                raise BatchPutScheduledActionsError(
                    f'Failed to put some actions: {put_response["FailedScheduledUpdateGroupActions"]}'
                )

    def configure_scheduled_scaling_rules(
        self,
        asg: AsgRuntimeInfo,
        schedule: ScheduleDefinition,
        period_store: PeriodDefinitionStore,
        running_state: AsgSize,
    ) -> datetime:
        """Configure scheduled scaling rules for an asg"""
        asg_name = asg.resource_id
        # convert this schedule to actions now to fail fast if the schedule is invalid
        # todo: this can fail -- need to handle failure with correct info tags
        new_schedule_actions: Final[list[ScheduledUpdateGroupActionRequestTypeDef]] = (
            list(
                schedule_to_actions(
                    schedule,
                    period_store,
                    running_state,
                    self.context.asg_scheduled_rule_prefix,
                )
            )
        )

        # futureproofing. future support for more advanced schedule rules (nth weekday) will only be valid for a limited time interval
        actions_valid_until = self.context.current_dt + timedelta(days=30)

        actions_backup: Final[list[ScheduledUpdateGroupActionRequestTypeDef]] = cast(
            list[ScheduledUpdateGroupActionRequestTypeDef],
            self.get_existing_scheduled_scaling_rules(asg_name=asg_name),
        )

        self._batch_delete_scheduled_action(
            scheduled_actions=actions_backup,
            auto_scaling_group_name=asg_name,
        )

        try:
            self._batch_put_scheduled_update_group_action(
                scheduled_update_group_actions=new_schedule_actions,
                auto_scaling_group_name=asg_name,
            )

            return actions_valid_until
        except Exception as update_exception:
            logger.error(
                f"Failed to configure group {asg_name} with schedule {schedule.name}, attempting rollback"
            )
            self._batch_put_scheduled_update_group_action(
                scheduled_update_group_actions=actions_backup,
                auto_scaling_group_name=asg_name,
            )

            raise update_exception

    def get_existing_scheduled_scaling_rules(
        self, asg_name: str
    ) -> list[ScheduledUpdateGroupActionTypeDef]:
        return list(
            filter(
                lambda action: action.get("ScheduledActionName", "").startswith(
                    self.context.asg_scheduled_rule_prefix
                ),
                self._describe_scheduled_actions(
                    auto_scaling_group_name=asg_name,
                ),
            )
        )


def schedule_to_actions(
    schedule_definition: ScheduleDefinition,
    period_store: PeriodDefinitionStore,
    steady_state: AsgSize,
    rule_prefix: str,
) -> Iterator[ScheduledUpdateGroupActionRequestTypeDef]:
    timezone: Final = schedule_definition.build_timezone()

    for period_definition in schedule_definition.fetch_period_definitions(period_store):
        yield from period_to_actions(
            period_definition, timezone, steady_state, rule_prefix
        )


def period_to_actions(
    period_definition: PeriodDefinition,
    timezone: ZoneInfo,
    steady_state: AsgSize,
    rule_prefix: str,
) -> Iterator[ScheduledUpdateGroupActionRequestTypeDef]:
    # ensure period names are always compatible with scheduled action names
    day_of_month: Final = to_asg_expr_monthdays(
        parse_monthdays_expr(period_definition.monthdays)
    )
    month_of_year: Final = to_asg_expr_months(
        parse_months_expr(period_definition.months)
    )
    day_of_week: Final = to_asg_expr_weekdays(
        parse_weekdays_expr(period_definition.weekdays)
    )

    if period_definition.begintime:
        begintime: Final = parse_time_str(period_definition.begintime)
        hour = begintime.hour
        minute = begintime.minute
        yield {
            "ScheduledActionName": f"{rule_prefix}{period_definition.name}Start",
            "Recurrence": f"{minute} {hour} {day_of_month} {month_of_year} {day_of_week}",
            "MinSize": steady_state.min_size,
            "MaxSize": steady_state.max_size,
            "DesiredCapacity": steady_state.desired_size,
            "TimeZone": str(timezone),
        }

    if period_definition.endtime:
        endtime: Final = parse_time_str(period_definition.endtime)
        hour = endtime.hour
        minute = endtime.minute
        yield {
            "ScheduledActionName": f"{rule_prefix}{period_definition.name}Stop",
            "Recurrence": f"{minute} {hour} {day_of_month} {month_of_year} {day_of_week}",
            "MinSize": 0,
            "MaxSize": 0,
            "DesiredCapacity": 0,
            "TimeZone": str(timezone),
        }
