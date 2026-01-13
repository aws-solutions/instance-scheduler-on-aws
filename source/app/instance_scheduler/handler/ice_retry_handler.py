# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import json
import traceback
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import (
    TYPE_CHECKING,
    Any,
    Final,
    TypeGuard,
)

from botocore.exceptions import ClientError
from instance_scheduler.configuration.scheduling_context import (
    SchedulingContext,
)
from instance_scheduler.handler.environments.ice_retry_request_environment import (
    IceErrorRequestEnvironment,
)
from instance_scheduler.observability.error_codes import ErrorCode
from instance_scheduler.observability.events import (
    report_scheduling_results_to_eventbus,
)
from instance_scheduler.observability.informational_tagging import (
    apply_informational_tags_for_results,
)
from instance_scheduler.observability.powertools_logging import (
    powertools_logger,
    should_log_events,
)
from instance_scheduler.scheduling.ec2.ec2 import Ec2Service, ManagedEC2Instance
from instance_scheduler.scheduling.ec2.ice_retry import IceRetryRequest
from instance_scheduler.scheduling.scheduling_decision import (
    ManagedInstance,
    RequestedAction,
    SchedulingDecision,
)
from instance_scheduler.scheduling.scheduling_result import SchedulingResult
from instance_scheduler.scheduling.states import InstanceState
from instance_scheduler.util import safe_json
from instance_scheduler.util.session_manager import AssumedRole, assume_role
from instance_scheduler.util.validation import (
    validate_string,
    validate_string_list,
)

if TYPE_CHECKING:
    from aws_lambda_powertools.utilities.typing import LambdaContext
    from mypy_boto3_sqs.type_defs import MessageTypeDef
else:
    LambdaContext = object
    InstanceTypeDef = object
    MessageTypeDef = object

logger: Final = powertools_logger()


def validate_ice_retry_request(
    untyped_dict: Mapping[str, Any],
) -> TypeGuard[IceRetryRequest]:
    validate_string(untyped_dict, "account", required=True)
    validate_string(untyped_dict, "region", required=True)
    validate_string(untyped_dict, "instance_id", required=True)
    validate_string_list(untyped_dict, "preferred_instance_types", required=True)

    return True


class InvalidRequestException(Exception):
    pass


class IceRetryEventException(Exception):
    pass


@logger.inject_lambda_context(log_event=should_log_events(logger))
def lambda_handler(
    event: Mapping[str, Any],
    lambda_context: LambdaContext,
) -> str:
    env = IceErrorRequestEnvironment.from_env()

    try:
        sqs_event: MessageTypeDef = event.get("Records", [])[0]
        ice_retry_event: IceRetryRequest = json.loads(str(sqs_event.get("body")))
        if validate_ice_retry_request(ice_retry_event):
            scheduling_context = build_scheduling_context(ice_retry_event, env)
            handler = IceRetryRequestHandler(
                ice_retry_event,
                env=env,
                scheduling_context=scheduling_context,
            )

            return handler.handle_request()
        else:
            raise InvalidRequestException("Invalid ice retry request")
    except Exception as error:
        logger.error(
            f"Error in lambda {lambda_context.function_name} handling ice retry request {safe_json(event)}: ({error})\n{traceback.format_exc()}",
        )
        raise error


def build_scheduling_context(
    event: IceRetryRequest, env: IceErrorRequestEnvironment
) -> SchedulingContext:
    current_dt = datetime.now(timezone.utc)
    role = assume_role(
        account=event["account"],
        region=event["region"],
        role_name=env.scheduler_role_name,
    )
    context = SchedulingContext(assumed_role=role, current_dt=current_dt, env=env)
    return context


class IceRetryRequestHandler:
    def __init__(
        self,
        event: IceRetryRequest,
        env: IceErrorRequestEnvironment,
        scheduling_context: SchedulingContext,
    ) -> None:
        self._event = event
        self._env = env
        self._scheduling_context = scheduling_context
        self._ec2_client = scheduling_context.assumed_role.client("ec2")

    def handle_request(self) -> str:
        event = self._event
        instance_id = event["instance_id"]
        with logger.append_context_keys(
            service="ec2",
            account=self._scheduling_context.assumed_role.account,
            region=self._scheduling_context.assumed_role.region,
        ):
            runtime_info = Ec2Service.describe_instance(
                self._scheduling_context.assumed_role, instance_id
            )

            if not runtime_info:
                raise IceRetryEventException(
                    f"Instance {instance_id} not found in account {self._scheduling_context.assumed_role.account} region {self._scheduling_context.assumed_role.region}"
                )

            registry_info = Ec2Service.fetch_or_create_registry_data(
                runtime_info,
                self._scheduling_context.registry,
                self._scheduling_context.schedule_tag_key,
            )
            managed_ec2 = ManagedEC2Instance(
                runtime_info=runtime_info,
                registry_info=registry_info,
            )

            result = attempt_ice_resize(
                role=self._scheduling_context.assumed_role,
                ec2_instance=managed_ec2,
                prioritized_types=event["preferred_instance_types"],
            )

            self._scheduling_context.registry.put(
                result.updated_registry_info,
                overwrite=True,
            )
            apply_informational_tags_for_results(
                self._scheduling_context.assumed_role,
                results=[result],
                hub_stack_arn=self._env.hub_stack_name,
            )
            report_scheduling_results_to_eventbus(
                results=[result],
                scheduling_role=self._scheduling_context.assumed_role,
                env=self._env,
            )

        return "OK"


def attempt_ice_resize(
    role: AssumedRole, ec2_instance: ManagedEC2Instance, prioritized_types: list[str]
) -> SchedulingResult[ManagedInstance]:
    ec2_client = role.client("ec2")
    decision: SchedulingDecision[ManagedInstance] = SchedulingDecision(
        instance=ec2_instance,
        action=RequestedAction.START,
        new_stored_state=InstanceState.RUNNING,
        reason="ICE Retry Requested",
    )

    for instance_type in prioritized_types:
        try:
            resize_instance(
                role,
                ec2_instance.runtime_info.resource_id,
                instance_type,
            )
            ec2_client.start_instances(
                InstanceIds=[ec2_instance.runtime_info.resource_id]
            )
            return SchedulingResult.success(decision)
        except ClientError as error:
            if error.response["Error"]["Code"] == "InsufficientInstanceCapacity":
                logger.debug(
                    f"{ec2_instance.arn}, failed to start with error InsufficientInstanceCapacity for instance type {instance_type}"
                )
                # try next type
                continue
            else:
                return SchedulingResult.client_exception(decision, error)

    # all types failed, insufficient capacity
    return SchedulingResult.shortcircuit_error(
        resource=ec2_instance,
        error_code=ErrorCode.START_FAILED,
        error_message=f"Insufficient Capacity for types {str.join(',', prioritized_types)}",
    )


def resize_instance(
    assumed_role: AssumedRole, instance_id: str, instance_type: str
) -> None:
    """
    change the instance type of the EC2 instance with ID in `instance` to
    `instance_type`
    """
    logger.info(f"resizing ec2 instance `{instance_id}` to `{instance_type}`")

    try:
        assumed_role.client("ec2").modify_instance_attribute(
            InstanceId=instance_id, InstanceType={"Value": instance_type}
        )
    except Exception as ex:
        logger.error(f"Error resizing instance {instance_id}, ({str(ex)})")
        raise ex
