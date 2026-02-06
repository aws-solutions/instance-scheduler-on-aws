# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from datetime import datetime, timezone
from typing import Iterable, TypeVar

from instance_scheduler.configuration.scheduling_context import (
    SchedulingContext,
    SchedulingEnvironment,
)
from instance_scheduler.model.managed_instance import (
    RegisteredAsgInstance,
    RegisteredEc2Instance,
    RegisteredRdsInstance,
)
from instance_scheduler.model.store.cached_period_definition_store import (
    CachedPeriodDefinitionStore,
)
from instance_scheduler.model.store.cached_schedule_definition_store import (
    CachedScheduleDefinitionStore,
)
from instance_scheduler.model.store.dynamo_resource_registry import (
    DynamoResourceRegistry,
)
from instance_scheduler.observability.error_codes import ErrorCode
from instance_scheduler.observability.events import (
    EventsBuffer,
)
from instance_scheduler.observability.events.resource_registration_events import (
    ResourceRegistrationEvent,
)
from instance_scheduler.observability.informational_tagging import (
    InfoTaggingContext,
    format_current_time,
)
from instance_scheduler.observability.powertools_logging import (
    LogContext,
    powertools_logger,
)
from instance_scheduler.observability.tag_keys import ControlTagKey
from instance_scheduler.scheduling.asg.asg_migration import (
    asg_needs_migration,
    migrate_asg,
)
from instance_scheduler.scheduling.asg.asg_runtime_info import AsgRuntimeInfo
from instance_scheduler.scheduling.asg.asg_service import AsgService
from instance_scheduler.scheduling.asg.asg_size import AsgSize
from instance_scheduler.scheduling.ec2.ec2 import EC2RuntimeInfo
from instance_scheduler.scheduling.rds.rds import RdsRuntimeInfo
from instance_scheduler.scheduling.states import InstanceState
from instance_scheduler.util.session_manager import AssumedRole

logger = powertools_logger()


T = TypeVar("T")


def register_ec2_resources(
    ec2_instances: Iterable[EC2RuntimeInfo],
    scheduling_role: AssumedRole,
    env: SchedulingEnvironment,
) -> None:
    registry = DynamoResourceRegistry(env.registry_table)

    with (
        InfoTaggingContext(scheduling_role, env.hub_stack_name) as tagging_context,
        EventsBuffer(scheduling_role, env) as event_buffer,
        logger.append_context_keys(
            context=LogContext.REGISTRATION.value,
            account=scheduling_role.account,
            region=scheduling_role.region,
        ),
    ):
        for ec2_instance in ec2_instances:
            registered_instance = RegisteredEc2Instance(
                account=ec2_instance.account,
                region=ec2_instance.region,
                resource_id=ec2_instance.resource_id,
                arn=ec2_instance.arn,
                name=ec2_instance.tags.get("Name", ""),
                schedule=ec2_instance.tags.get(env.schedule_tag_key, ""),
                stored_state=InstanceState.UNKNOWN,
            )

            registry.put(registered_instance, overwrite=True)
            tagging_context.push_info_tag_update([ec2_instance])
            event_buffer.push(
                ResourceRegistrationEvent.for_resource(
                    registered_instance
                ).as_event_bus_event()
            )
            logger.info(
                f"Registered EC2 instance: {registered_instance.arn}",
                resource=registered_instance.arn,
            )


def deregister_ec2_resources(
    ec2_instances: Iterable[RegisteredEc2Instance],
    scheduler_role: AssumedRole,
    env: SchedulingEnvironment,
) -> None:
    registry = DynamoResourceRegistry(env.registry_table)
    with (
        InfoTaggingContext(scheduler_role, env.hub_stack_name) as tagging_context,
        logger.append_context_keys(
            context=LogContext.REGISTRATION.value,
            account=scheduler_role.account,
            region=scheduler_role.region,
        ),
    ):
        for registered_ec2 in ec2_instances:
            registry.delete(registered_ec2.key, error_if_missing=False)
            tagging_context.push_clear_info_tags(registered_ec2.arn)
            logger.info(
                f"Deregistered EC2 instance: {registered_ec2.arn}",
                resource=registered_ec2.arn,
            )


def register_rds_resources(
    rds_resources: Iterable[RdsRuntimeInfo],
    scheduling_role: AssumedRole,
    env: SchedulingEnvironment,
) -> None:
    registry = DynamoResourceRegistry(env.registry_table)
    current_time = format_current_time()

    with (
        InfoTaggingContext(scheduling_role, env.hub_stack_name) as tagging_context,
        EventsBuffer(scheduling_role, env) as event_buffer,
        logger.append_context_keys(
            context=LogContext.REGISTRATION.value,
            account=scheduling_role.account,
            region=scheduling_role.region,
        ),
    ):
        for rds_resource in rds_resources:
            is_supported, reason = rds_resource.check_if_is_supported()
            if not is_supported:
                tagging_context.push_info_tag_update(
                    [rds_resource],
                    error_code=f"{ErrorCode.UNSUPPORTED_RESOURCE.value} ({current_time})",
                    error_message=reason,
                )

                logger.info(
                    f"Unable to register RDS resource {rds_resource.arn}. Unsupported Resource: {reason}",
                    resource=rds_resource.arn,
                )
                continue

            registered_instance = RegisteredRdsInstance(
                account=scheduling_role.account,
                region=scheduling_role.region,
                resource_id=rds_resource.resource_id,
                arn=rds_resource.arn,
                schedule=rds_resource.tags.get(env.schedule_tag_key, ""),
                name=rds_resource.name,
                stored_state=InstanceState.UNKNOWN,
            )

            registry.put(registered_instance, overwrite=True)
            tagging_context.push_info_tag_update([rds_resource])
            event_buffer.push(
                ResourceRegistrationEvent.for_resource(
                    registered_instance
                ).as_event_bus_event()
            )
            logger.info(
                f"Registered RDS resource: {registered_instance.arn}",
                resource=registered_instance.arn,
            )


def deregister_rds_resources(
    rds_resources: Iterable[RegisteredRdsInstance],
    scheduler_role: AssumedRole,
    env: SchedulingEnvironment,
) -> None:
    registry = DynamoResourceRegistry(env.registry_table)
    with (
        InfoTaggingContext(scheduler_role, env.hub_stack_name) as tagging_context,
        logger.append_context_keys(
            context=LogContext.REGISTRATION.value,
            account=scheduler_role.account,
            region=scheduler_role.region,
        ),
    ):
        for registered_rds in rds_resources:
            registry.delete(registered_rds.key, error_if_missing=False)
            tagging_context.push_clear_info_tags(registered_rds.arn)
            logger.info(
                f"Deregistered RDS resource: {registered_rds.arn}",
                resource=registered_rds.arn,
            )


def register_asg_resources(
    asg_resources: Iterable[AsgRuntimeInfo],
    scheduling_role: AssumedRole,
    env: SchedulingEnvironment,
) -> None:
    registry = DynamoResourceRegistry(env.registry_table)
    schedule_store = CachedScheduleDefinitionStore(env.config_table)
    period_store = CachedPeriodDefinitionStore(env.config_table)
    current_time = format_current_time()

    with (
        InfoTaggingContext(scheduling_role, env.hub_stack_name) as tagging_context,
        EventsBuffer(scheduling_role, env) as event_buffer,
        logger.append_context_keys(
            context=LogContext.REGISTRATION.value,
            account=scheduling_role.account,
            region=scheduling_role.region,
        ),
    ):
        for asg_resource in asg_resources:
            if asg_needs_migration(asg_resource, env):
                migrate_asg(asg_resource, scheduling_role, env)

            registered_instance = RegisteredAsgInstance(
                account=scheduling_role.account,
                region=scheduling_role.region,
                resource_id=asg_resource.resource_id,
                arn=asg_resource.arn,
                schedule=asg_resource.tags.get(env.schedule_tag_key, ""),
                name=asg_resource.tags.get("Name", ""),
                stored_state=InstanceState.UNKNOWN,
                last_configured=None,
            )

            registry.put(registered_instance, overwrite=True)
            logger.info(
                f"Registered ASG: {asg_resource.arn}", resource=asg_resource.arn
            )

            # schedules can be modified by the customer later, so this check happens after the ASG is registered

            schedule = schedule_store.find_by_name(registered_instance.schedule)

            if schedule is None:
                tagging_context.push_info_tag_update(
                    [asg_resource],
                    error_code=f"{ErrorCode.UNKNOWN_SCHEDULE.value} ({current_time})",
                    error_message="Unknown Schedule",
                )
            else:
                is_compatible, reason = AsgService.is_compatibile_schedule(
                    schedule, period_store
                )

                if not is_compatible:
                    tagging_context.push_info_tag_update(
                        [asg_resource],
                        error_code=f"{ErrorCode.INCOMPATIBLE_SCHEDULE.value} ({current_time})",
                        error_message=reason,
                    )
                else:
                    if not asg_resource.tags.get(ControlTagKey.MIN_DESIRED_MAX):
                        tagging_context.push_info_tag_update(
                            [asg_resource],
                            additional_tags={
                                ControlTagKey.MIN_DESIRED_MAX.value: AsgSize.from_group(
                                    asg_resource.group
                                ).to_mdm_str()
                            },
                        )
                    else:
                        tagging_context.push_info_tag_update([asg_resource])

            event_buffer.push(
                ResourceRegistrationEvent.for_resource(
                    registered_instance
                ).as_event_bus_event()
            )


@logger.append_context_keys(context=LogContext.REGISTRATION.value)
def deregister_asg_resources(
    asg_resources: Iterable[RegisteredAsgInstance],
    scheduling_role: AssumedRole,
    env: SchedulingEnvironment,
) -> None:
    scheduling_context = SchedulingContext(
        assumed_role=scheduling_role, current_dt=datetime.now(timezone.utc), env=env
    )

    asg_service = AsgService(scheduling_context)
    registry = DynamoResourceRegistry(env.registry_table)

    with (
        InfoTaggingContext(scheduling_role, env.hub_stack_name) as tagging_context,
        logger.append_context_keys(
            account=scheduling_role.account, region=scheduling_role.region
        ),
    ):
        for asg in asg_resources:
            asg_service.delete_existing_scheduled_actions(asg.resource_id)
            tagging_context.push_clear_info_tags(asg.arn)
            registry.delete(asg.key, error_if_missing=False)
            logger.info(f"Deregistered ASG: {asg.arn}", resource=asg.arn)
