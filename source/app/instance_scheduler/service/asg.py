# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import json
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Final, List, Optional
from zoneinfo import ZoneInfo

from aws_lambda_powertools.logging import Logger

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
from instance_scheduler.model.period_definition import PeriodDefinition
from instance_scheduler.model.schedule_definition import ScheduleDefinition
from instance_scheduler.util.session_manager import AssumedRole
from instance_scheduler.util.validation import (
    ValidationException,
    require_int,
    require_str,
)

if TYPE_CHECKING:
    from mypy_boto3_autoscaling.client import AutoScalingClient
    from mypy_boto3_autoscaling.type_defs import (
        AutoScalingGroupTypeDef,
        ScheduledUpdateGroupActionRequestTypeDef,
        ScheduledUpdateGroupActionTypeDef,
        TagDescriptionTypeDef,
    )
else:
    AutoScalingClient = object
    ScheduledUpdateGroupActionRequestTypeDef = object
    ScheduledUpdateGroupActionTypeDef = object
    TagDescriptionTypeDef = object
    AutoScalingGroupTypeDef = object

logger: Final = Logger(log_uncaught_exceptions=True, use_rfc3339=True)


class AsgTagValidationError(Exception):
    pass


class BatchDeleteScheduledActionsError(Exception):
    pass


class BatchPutScheduledActionsError(Exception):
    pass


class RollbackFailed(Exception):
    pass


class InvalidSteadyState(Exception):
    pass


@dataclass(frozen=True)
class AsgTag:
    schedule: str
    ttl: str
    min_size: int
    max_size: int
    desired_size: int

    @classmethod
    def from_group(
        cls,
        *,
        group: AutoScalingGroupTypeDef,
        asg_scheduled_tag_key: str,
    ) -> "AsgTag":
        """
        Return an auto scaling group scheduled tag configured by the solution if existing.
        When validation fails, raise "AsgValidationError".

        :param group: an auto scaling group
        :param asg_scheduled_tag_key: an auto scaling scheduled tag key ("scheduled" by default)
        :return: the auto scaling group scheduled tag
        """

        scheduled_tags: Final[List[TagDescriptionTypeDef]] = list(
            filter(
                lambda tag: tag.get("Key") == asg_scheduled_tag_key,
                group.get("Tags", []),
            )
        )

        if len(scheduled_tags) == 0:
            raise AsgTagValidationError("Scheduled tag missing")
        return AsgTag.from_json(scheduled_tags[0].get("Value", ""))

    def is_still_valid(
        self, *, schedule_name: str, is_schedule_override: bool
    ) -> tuple[bool, str]:
        """
        Check if the auto scaling group scheduled tag is still valid.
        This decides if the auto scaling group needs to be scheduled or updated.
        If any of the following are true, the group needs to be updated:
        1. the schedule as changed, so we need to override
        2. the tag we applied is for a different schedule
        3. the tag we applied is nearing expiration

        :param schedule_name: a schedule name
        :param is_schedule_override: a flag to check if it is to override the schedule or not
        :return: if the auto scaling group scheduled tag is valid and a reason behind the decision
        """

        if is_schedule_override:
            return False, "Overridden"

        configured_schedule: Final = self.schedule

        if configured_schedule != schedule_name:
            return False, "Configured for a different schedule"

        ttl: Final[str] = self.ttl

        try:
            ttl_dt = datetime.fromisoformat(ttl)
        except Exception:
            return False, "Unable to parse configuration TTL"

        if ttl_dt < datetime.now(timezone.utc) + timedelta(days=1):
            return False, "Configuration expiring in less than one day"

        return (
            True,
            f"All conditions met, current config valid for schedule {schedule_name} until {ttl_dt.isoformat()}",
        )

    def to_json(self) -> str:
        return json.dumps(
            {
                "schedule": self.schedule,
                "ttl": self.ttl,
                "min_size": self.min_size,
                "max_size": self.max_size,
                "desired_size": self.desired_size,
            }
        )

    @classmethod
    def from_json(cls, json_str: str) -> "AsgTag":
        try:
            json_data: Final = json.loads(json_str)
        except Exception:
            raise AsgTagValidationError("Unable to parse Scheduled tag value")

        if not isinstance(json_data, dict):
            raise AsgTagValidationError("Invalid Scheduled tag value: not a dict")

        try:
            return AsgTag(
                schedule=require_str(json_data, "schedule"),
                ttl=require_str(json_data, "ttl"),
                min_size=require_int(json_data, "min_size"),
                max_size=require_int(json_data, "max_size"),
                desired_size=require_int(json_data, "desired_size"),
            )
        except ValidationException as e:
            raise AsgTagValidationError(f"Invalid Scheduled tag value: {e}") from e


@dataclass(frozen=True)
class AsgSize:
    min_size: int
    desired_size: int
    max_size: int

    def is_stopped_state(self) -> bool:
        return self.min_size == 0 and self.desired_size == 0 and self.max_size == 0

    def __str__(self) -> str:
        return f"{self.min_size}-{self.desired_size}-{self.max_size}"

    @classmethod
    def from_group(cls, group: AutoScalingGroupTypeDef) -> "AsgSize":
        return AsgSize(
            min_size=group["MinSize"],
            desired_size=group["DesiredCapacity"],
            max_size=group["MaxSize"],
        )

    @classmethod
    def from_tag(cls, asg_tag: AsgTag) -> "AsgSize":
        """
        Get an auto scaling group size from a scheduled tag configured by the solution.
        When any size value is invalid, return stopped size so it can't be scheduled with tag values.

        :param asg_tag: a scheduled tag value configured by the solution
        :return: the auto scaling group size
        """

        return AsgSize(
            min_size=asg_tag.min_size,
            desired_size=asg_tag.desired_size,
            max_size=asg_tag.max_size,
        )

    @classmethod
    def stopped(cls) -> "AsgSize":
        return AsgSize(min_size=0, desired_size=0, max_size=0)


class AsgService:
    def __init__(
        self,
        *,
        assumed_asg_scheduling_role: AssumedRole,
        schedule_tag_key: str,
        asg_scheduled_tag_key: str,
        rule_prefix: str,
    ) -> None:
        self._schedule_tag_key: Final = schedule_tag_key
        self._asg_scheduled_tag_key: Final = asg_scheduled_tag_key
        self._rule_prefix: Final = rule_prefix
        self._autoscaling: Final[AutoScalingClient] = (
            assumed_asg_scheduling_role.client("autoscaling")
        )

    def get_schedulable_groups(
        self, schedule_names: list[str] | None = None
    ) -> Iterator[AutoScalingGroupTypeDef]:
        paginator: Final = self._autoscaling.get_paginator(
            "describe_auto_scaling_groups"
        )

        if schedule_names is None:
            for page in paginator.paginate(
                Filters=[{"Name": "tag-key", "Values": [self._schedule_tag_key]}]
            ):
                yield from page["AutoScalingGroups"]
        else:
            batch_size = 5  # maximum number of schedule names that can be requested in a single describe call
            for i in range(0, len(schedule_names), batch_size):
                batch = schedule_names[i : i + batch_size]
                for page in paginator.paginate(
                    Filters=[{"Name": f"tag:{self._schedule_tag_key}", "Values": batch}]
                ):
                    yield from page["AutoScalingGroups"]

    def schedule_auto_scaling_group(
        self,
        group: AutoScalingGroupTypeDef,
        schedule_definition: ScheduleDefinition,
        period_definitions: list[PeriodDefinition],
        is_schedule_override: bool = False,
    ) -> None:
        """
        Schedule an auto scaling group.
        An auto scaling group can be scheduled at least one of the following is true:
        1. the solution configured tag (auto scaling scheduled tag) should not be valid anymore.
        2. when a data in the config DynamoDB table changes, it overrides the schedule with new schedule definitions.
        3. auto scaling sizes should not be stopped.

        :param group: an auto scaling group
        :param schedule_definition: a schedule definition
        :param period_definitions: scheduling period definitions
        :param is_schedule_override: a flag to check if it is to override the schedule or not
        """

        auto_scaling_group_name: Final = group["AutoScalingGroupName"]

        try:
            asg_tag = AsgTag.from_group(
                group=group, asg_scheduled_tag_key=self._asg_scheduled_tag_key
            )
            valid, reason = asg_tag.is_still_valid(
                schedule_name=schedule_definition.name,
                is_schedule_override=is_schedule_override,
            )

            if valid:
                logger.info(
                    f"Skipping group {auto_scaling_group_name} with schedule {schedule_definition.name}: {reason}"
                )
            else:
                self._reconfigure_scheduled_actions_to_match_schedule(
                    asg=group,
                    schedule=schedule_definition,
                    period_definitions=period_definitions,
                    asg_tag=asg_tag,
                )

        except AsgTagValidationError as e:
            logger.info(f"Invalid Scheduled Tag: {e}")
            self._reconfigure_scheduled_actions_to_match_schedule(
                asg=group,
                schedule=schedule_definition,
                period_definitions=period_definitions,
            )
        except Exception as e:
            logger.error(f"Error scheduling autoscaling group: {e}")

    def _get_steady_state(
        self, group: AutoScalingGroupTypeDef, asg_tag: Optional[AsgTag] = None
    ) -> AsgSize:
        """
        Get the steady state of an auto scaling group size to be scheduled.
        The current size on the auto scaling group is prioritized.

        :param group: an auto scaling group
        :param asg_tag: an auto scaling group scheduled tag value
        :return: steady state of the auto scaling group
        """

        current_size: Final = AsgSize.from_group(group=group)
        tag_size: Final = (
            AsgSize.from_tag(asg_tag=asg_tag) if asg_tag else AsgSize.stopped()
        )

        if not current_size.is_stopped_state():
            return current_size

        return tag_size

    def _describe_scheduled_actions(
        self, auto_scaling_group_name: str
    ) -> Iterator[ScheduledUpdateGroupActionTypeDef]:
        """
        Generator to get existing scheduled actions from an auto scaling group.
        It returns existing scheduled update group actions on an auto scaling group.

        :param auto_scaling_group_name: auto scaling group name
        :return: a scheduled action
        """

        paginator: Final = self._autoscaling.get_paginator("describe_scheduled_actions")

        for page in paginator.paginate(AutoScalingGroupName=auto_scaling_group_name):
            for action in page["ScheduledUpdateGroupActions"]:
                yield action

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
            delete_response = self._autoscaling.batch_delete_scheduled_action(
                AutoScalingGroupName=auto_scaling_group_name,
                ScheduledActionNames=list(
                    action["ScheduledActionName"] for action in scheduled_actions
                ),
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
            put_response = self._autoscaling.batch_put_scheduled_update_group_action(
                AutoScalingGroupName=auto_scaling_group_name,
                ScheduledUpdateGroupActions=scheduled_update_group_actions,
            )

            # creating individual actions may fail, need to check response
            if len(put_response["FailedScheduledUpdateGroupActions"]) > 0:
                raise BatchPutScheduledActionsError(
                    f'Failed to put some actions: {put_response["FailedScheduledUpdateGroupActions"]}'
                )

    def _reconfigure_scheduled_actions_to_match_schedule(
        self,
        asg: AutoScalingGroupTypeDef,
        schedule: ScheduleDefinition,
        period_definitions: list[PeriodDefinition],
        asg_tag: Optional[AsgTag] = None,
    ) -> None:
        """
        Reconfigure an asg's scheduled scaling rules to match a given schedule
        1. Delete all existing scheduled actions configured by the solution previously.
        2. Put new or updated scheduled actions configured by the solution.
        3. Create or update the auto scaling tag to have a solution configured tag.

        When 1 fails, it does not require rollback as there is no resource to revert.
        When 2 or 3 fails, rollback to the previously scheduled actions is attempted.
        """

        asg_group_name = asg["AutoScalingGroupName"]
        steady_state = self._get_steady_state(group=asg, asg_tag=asg_tag)

        if steady_state.is_stopped_state():
            raise InvalidSteadyState('Unable to determine valid "running" state')

        logger.info(
            f"Configuring group {asg_group_name} with schedule {schedule.name}. Using {steady_state} as running state"
        )

        # convert this schedule to actions now to fail fast if the schedule is invalid
        new_schedule_actions: Final[list[ScheduledUpdateGroupActionRequestTypeDef]] = (
            list(
                schedule_to_actions(
                    schedule,
                    period_definitions,
                    steady_state,
                    self._rule_prefix,
                )
            )
        )

        existing_actions_configured_by_solution: Final[
            list[ScheduledUpdateGroupActionTypeDef]
        ] = list(
            filter(
                lambda action: action.get("ScheduledActionName", "").startswith(
                    self._rule_prefix
                ),
                self._describe_scheduled_actions(
                    auto_scaling_group_name=asg_group_name,
                ),
            )
        )

        self._batch_delete_scheduled_action(
            scheduled_actions=existing_actions_configured_by_solution,
            auto_scaling_group_name=asg_group_name,
        )

        try:
            self._batch_put_scheduled_update_group_action(
                scheduled_update_group_actions=new_schedule_actions,
                auto_scaling_group_name=asg_group_name,
            )

            self._autoscaling.create_or_update_tags(
                Tags=[
                    {
                        "ResourceType": "auto-scaling-group",
                        "ResourceId": asg_group_name,
                        "Key": self._asg_scheduled_tag_key,
                        "Value": AsgTag(
                            schedule=schedule.name,
                            ttl=(
                                datetime.now(timezone.utc) + timedelta(days=30)
                            ).isoformat(),
                            min_size=steady_state.min_size,
                            max_size=steady_state.max_size,
                            desired_size=steady_state.desired_size,
                        ).to_json(),
                        "PropagateAtLaunch": False,
                    }
                ]
            )
        except Exception as update_exception:
            logger.error(
                f"Failed to configure group {asg_group_name} with schedule {schedule.name}, attempting rollback"
            )

            try:
                self._rollback_asg_update(
                    asg_name=asg_group_name,
                    original_actions=existing_actions_configured_by_solution,
                    new_actions_to_rollback=new_schedule_actions,
                )
                logger.info(f"rollback of {asg_group_name} complete")
            except Exception as rollback_exception:
                logger.error(f"rollback failed: {rollback_exception}")

            raise update_exception

    def _rollback_asg_update(
        self,
        asg_name: str,
        original_actions: List[ScheduledUpdateGroupActionTypeDef],
        new_actions_to_rollback: List[ScheduledUpdateGroupActionRequestTypeDef],
    ) -> None:
        """
        rollback a failed asg update
        """
        try:
            self._batch_delete_scheduled_action(
                scheduled_actions=new_actions_to_rollback,
                auto_scaling_group_name=asg_name,
            )
        except Exception as e:
            raise RollbackFailed("RollbackFailed: Failed to delete some actions") from e

        try:
            self._batch_put_scheduled_update_group_action(
                scheduled_update_group_actions=list(
                    action_description_to_request(original_actions)
                ),
                auto_scaling_group_name=asg_name,
            )
        except Exception as e:
            raise RollbackFailed(
                "RollbackFailed: Failed to restore some actions"
            ) from e


def action_description_to_request(
    actions: Iterable[ScheduledUpdateGroupActionTypeDef],
) -> Iterator[ScheduledUpdateGroupActionRequestTypeDef]:
    for action in actions:
        result: ScheduledUpdateGroupActionRequestTypeDef = {
            "ScheduledActionName": action["ScheduledActionName"]
        }
        if "StartTime" in action:
            result["StartTime"] = action["StartTime"]
        if "EndTime" in action:
            result["EndTime"] = action["EndTime"]
        if "Recurrence" in action:
            result["Recurrence"] = action["Recurrence"]
        if "MinSize" in action:
            result["MinSize"] = action["MinSize"]
        if "DesiredCapacity" in action:
            result["DesiredCapacity"] = action["DesiredCapacity"]
        if "MaxSize" in action:
            result["MaxSize"] = action["MaxSize"]
        if "TimeZone" in action:
            result["TimeZone"] = action["TimeZone"]
        yield result


def schedule_to_actions(
    schedule_definition: ScheduleDefinition,
    period_definitions: list[PeriodDefinition],
    steady_state: AsgSize,
    rule_prefix: str,
) -> Iterator[ScheduledUpdateGroupActionRequestTypeDef]:
    timezone: Final = schedule_definition.build_timezone()

    for period_definition in period_definitions:
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
