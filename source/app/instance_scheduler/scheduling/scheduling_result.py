# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from dataclasses import dataclass, replace
from enum import Enum
from typing import Generic, Optional, TypeVar, assert_never

from botocore.exceptions import ClientError
from instance_scheduler.model.managed_instance import RegisteredInstance
from instance_scheduler.observability.error_codes import ErrorCode
from instance_scheduler.scheduling.scheduling_decision import (
    ManagedInstance,
    RequestedAction,
    SchedulingDecision,
)
from instance_scheduler.scheduling.states import InstanceState

T = TypeVar("T", bound=ManagedInstance)


class SchedulingAction(Enum):
    DO_NOTHING = None
    START = "Started"
    STOP = "Stopped"
    HIBERNATE = "Hibernated"
    CONFIGURE = "Configured"
    ERROR = "Error"

    @classmethod
    def from_requested_action(
        cls, requested_action: RequestedAction
    ) -> "SchedulingAction":
        match requested_action:
            case RequestedAction.START:
                return SchedulingAction.START
            case RequestedAction.STOP:
                return SchedulingAction.STOP
            case RequestedAction.DO_NOTHING:
                return SchedulingAction.DO_NOTHING
            case RequestedAction.CONFIGURE:
                return SchedulingAction.CONFIGURE
            case _:
                assert_never(requested_action)


@dataclass()
class SchedulingResult(Generic[T]):
    instance: T
    updated_registry_info: RegisteredInstance
    requested_action: Optional[RequestedAction]
    request_reason: Optional[str]
    action_taken: Optional[SchedulingAction]
    action_info: Optional[str] = None
    error_code: Optional[ErrorCode] = None
    error_message: Optional[str] = None

    def to_json_log(self) -> dict[str, str]:
        return {
            "log_type": "scheduling_result",
            "resource": self.instance.arn,
            "schedule": self.instance.registry_info.schedule,
            "instance_type": self.instance.runtime_info.size,
            "decision": (
                str(self.requested_action.value) if self.requested_action else ""
            ),
            "reason": str(self.request_reason),
            "action_taken": (
                str(self.action_taken.value) if self.action_taken else "None"
            ),
            "action_info": str(self.action_info),
            "error_code": str(self.error_code.value) if self.error_code else "",
            "error_message": str(self.error_message),
        }

    @classmethod
    def no_action_needed(
        cls,
        decision: SchedulingDecision[T],
        reason: str = "",
        updated_registry_info: Optional[RegisteredInstance] = None,
    ) -> "SchedulingResult[T]":
        # historical -- scheduling decisions specify a new state that should be stored in the registry, but ASGs function
        # differently. this fallback simplifies EC2 and RDS somewhat until this can be better refactored later
        if not updated_registry_info:
            updated_registry_info = replace(
                decision.instance.registry_info, stored_state=decision.new_stored_state
            )

        return cls(
            instance=decision.instance,
            requested_action=decision.action,
            request_reason=decision.reason,
            action_taken=SchedulingAction.DO_NOTHING,
            action_info=reason,
            updated_registry_info=updated_registry_info,
        )

    @classmethod
    def success(
        cls,
        decision: SchedulingDecision[T],
        action_taken: Optional[SchedulingAction] = None,
        updated_registry_info: Optional[RegisteredInstance] = None,
    ) -> "SchedulingResult[T]":

        # historical -- scheduling decisions specify a new state that should be stored in the registry, but ASGs function
        # differently. this fallback simplifies EC2 and RDS somewhat until this can be better refactored later
        if not updated_registry_info:
            updated_registry_info = replace(
                decision.instance.registry_info, stored_state=decision.new_stored_state
            )

        return cls(
            instance=decision.instance,
            requested_action=decision.action,
            request_reason=decision.reason,
            action_taken=action_taken
            or SchedulingAction.from_requested_action(decision.action),
            updated_registry_info=updated_registry_info,
        )

    @classmethod
    def error(
        cls,
        resource: T,
        error_code: ErrorCode,
        error_message: Optional[str] = None,
        updated_registry_info: Optional[RegisteredInstance] = None,
    ) -> "SchedulingResult[T]":
        return cls(
            instance=resource,
            requested_action=None,
            request_reason=None,
            action_taken=SchedulingAction.ERROR,
            error_code=error_code,
            error_message=error_message,
            updated_registry_info=updated_registry_info or resource.registry_info,
        )

    @classmethod
    def client_exception(
        cls,
        decision: SchedulingDecision[T],
        error: Optional[Exception] = None,
        updated_registry_info: Optional[RegisteredInstance] = None,
    ) -> "SchedulingResult[T]":
        match decision.action:
            case RequestedAction.START:
                error_code = ErrorCode.START_FAILED
                failure_state = InstanceState.START_FAILED
            case RequestedAction.STOP:
                error_code = ErrorCode.STOP_FAILED
                failure_state = InstanceState.STOP_FAILED
            case RequestedAction.CONFIGURE:
                error_code = ErrorCode.CONFIGURATION_FAILED
                failure_state = InstanceState.CONFIGURATION_FAILED
            case _:
                error_code = ErrorCode.UNKNOWN_ERROR
                failure_state = decision.new_stored_state

        # historical -- scheduling decisions specify a new state that should be stored in the registry, but ASGs function
        # differently. this fallback simplifies EC2 and RDS somewhat until this can be better refactored later
        if not updated_registry_info:
            updated_registry_info = replace(
                decision.instance.registry_info, stored_state=failure_state
            )

        return cls(
            instance=decision.instance,
            requested_action=decision.action,
            request_reason=decision.reason,
            action_taken=SchedulingAction.ERROR,
            error_code=error_code,
            error_message=(
                error.__str__() if isinstance(error, ClientError) else "Unknown Error"
            ),
            updated_registry_info=updated_registry_info,
        )
