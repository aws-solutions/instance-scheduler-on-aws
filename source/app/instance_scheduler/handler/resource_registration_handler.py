# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from typing import Any, Dict, List, Optional, cast

from instance_scheduler.handler.environments.resource_registration_environment import (
    ResourceRegistrationEnvironment,
)
from instance_scheduler.model.managed_instance import (
    RegisteredAsgInstance,
    RegistryKey,
)
from instance_scheduler.model.store.dynamo_resource_registry import (
    DynamoResourceRegistry,
)
from instance_scheduler.observability.informational_tagging import (
    clear_informational_tags,
)
from instance_scheduler.observability.powertools_logging import (
    LogContext,
    powertools_logger,
)
from instance_scheduler.scheduling.asg.asg_service import AsgService
from instance_scheduler.scheduling.ec2 import Ec2Service
from instance_scheduler.scheduling.rds import RdsService
from instance_scheduler.scheduling.resource_registration import (
    deregister_asg_resources,
    deregister_ec2_resources,
    deregister_rds_resources,
    register_asg_resources,
    register_ec2_resources,
    register_rds_resources,
)
from instance_scheduler.util.arn import ARN
from instance_scheduler.util.session_manager import assume_role
from pydantic import BaseModel, Field

logger = powertools_logger()

env = ResourceRegistrationEnvironment.from_env()
registry = DynamoResourceRegistry(env.registry_table)


class ResourceRegistrationEventDetail(BaseModel):
    service: str
    changed_tag_keys: list[str] = Field(default=[], alias="changed-tag-keys")
    tags: Dict[str, str] = {}
    resource_type: str = Field(alias="resource-type")


class ResourceRegistrationEvent(BaseModel):
    account: str
    region: str
    resources: List[str]
    detail: ResourceRegistrationEventDetail


class AsgTag(BaseModel):
    resourceId: str
    resourceType: str
    key: str
    value: str
    propagateAtLaunch: bool


class RegistrationFailureException(Exception):
    pass


class AsgRequestParameters(BaseModel):
    tags: List[AsgTag]


class AsgEventDetail(BaseModel):
    eventSource: str
    eventName: str
    requestParameters: AsgRequestParameters


class AsgRegistrationEvent(BaseModel):
    account: str
    region: str
    detail: AsgEventDetail


@logger.inject_lambda_context(log_event=True, clear_state=True)
def lambda_handler(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    """Route events to appropriate handlers based on source."""
    try:
        match event.get("source"):
            case "aws.autoscaling":
                validated_asg_event = AsgRegistrationEvent(**event)
                return handle_asg_tagging_event(validated_asg_event)
            case "aws.tag":
                validated_tagging_event = ResourceRegistrationEvent(**event)
                return handle_tagging_event(validated_tagging_event)
            case _:
                error_msg = f"Unsupported event source: {event.get('source')}"
                logger.error(error_msg)
                raise ValueError(error_msg)
    except Exception as e:
        logger.error(f"Failed to process event: {e}")
        raise


def handle_tagging_event(event: ResourceRegistrationEvent) -> Dict[str, Any]:
    """Handle regular EventBridge tagging events."""
    # Check if event has schedule tag

    logger.append_keys(
        context=LogContext.REGISTRATION.value,
        account=event.account,
        region=event.region,
        service=event.detail.service,
    )

    failed_resources: list[str] = []
    for resource_arn in event.resources:
        resource_arn = ARN(resource_arn)
        logger.append_keys(instance=resource_arn)
        skip_resource: bool = False
        match event.detail.service:
            case "ec2":
                skip_resource = process_ec2_instance_or_skip(
                    event, resource_arn, failed_resources
                )
            case "rds":
                skip_resource = process_rds_instance_or_skip(
                    event, resource_arn, failed_resources
                )
            case _:
                logger.warning(f"Unsupported service type: {event.detail.service}")

        if skip_resource:
            continue
    if failed_resources:
        raise RegistrationFailureException(
            f"Failed to register resources: {failed_resources}"
        )
    return {"statusCode": 200, "body": "Resources processed successfully"}


def process_rds_instance_or_skip(
    event: ResourceRegistrationEvent, resource_arn: ARN, failed_resources: list[str]
) -> bool:
    if event.detail.resource_type not in ["cluster", "db"]:
        logger.debug(
            f"event for unsupported rds resource_type. skipping...: {event.detail.resource_type}"
        )
        return True  # skip

    scheduling_role = assume_role(
        account=event.account,
        region=event.region,
        role_name=env.scheduler_role_name,
    )

    if is_schedule_tag_deletion_event(event):
        deregister_rds_resources(
            filter(None, [registry.get(RegistryKey.from_arn(resource_arn))]),  # type: ignore
            scheduling_role,
            env,
        )
    else:

        rds_resource = RdsService.describe_rds_resource(scheduling_role, resource_arn)

        if not rds_resource:
            # this can occur when describing cluster members...
            logger.error(f"Could not find resource for registration {resource_arn}")
            failed_resources.append(resource_arn)
            return True

        register_rds_resources(
            [rds_resource],
            scheduling_role,
            env,
        )
    return False


def process_ec2_instance_or_skip(
    event: ResourceRegistrationEvent, resource_arn: ARN, failed_resources: list[str]
) -> bool:
    if ec2_tagging_event_is_for_asg(event):
        logger.debug(f"ec2 member of asg. skipping...: {event.detail.service}")
        return True

    scheduling_role = assume_role(
        account=event.account,
        region=event.region,
        role_name=env.scheduler_role_name,
    )

    if is_schedule_tag_deletion_event(event):
        deregister_ec2_resources(
            filter(None, [registry.get(RegistryKey.from_arn(resource_arn))]),  # type: ignore
            scheduling_role,
            env,
        )
    else:
        instance_runtime_info = Ec2Service.describe_instance(
            scheduling_role, resource_arn.resource_id
        )

        if not instance_runtime_info:
            logger.error(f"Could not find instance for registration {resource_arn}")
            failed_resources.append(resource_arn)
            return True

        register_ec2_resources(
            [instance_runtime_info],
            scheduling_role,
            env,
        )
    return False


def ec2_tagging_event_is_for_asg(event: ResourceRegistrationEvent) -> bool:
    """Check if the event is for an ASG."""
    if event.detail.tags.get("aws:autoscaling:groupName"):
        return True

    if "aws:autoscaling:groupName" in event.detail.changed_tag_keys:
        return True

    return False


def is_schedule_tag_deletion_event(event: ResourceRegistrationEvent) -> bool:
    """Check if the event is a deletion event."""
    return event.detail.tags.get(env.schedule_tag_key) is None


def _deregister_resource(resource_arn: ARN) -> None:
    """Handle resource deregistration."""
    # Assume role into source account
    assumed_role = assume_role(
        account=resource_arn.account,
        region=resource_arn.region,
        role_name=env.scheduler_role_name,
    )

    if resource_arn.service not in ["ec2", "rds"]:
        logger.warning(f"Unsupported service type: {resource_arn.service}")
        return

    registry.delete(
        RegistryKey.from_arn(resource_arn),
        error_if_missing=False,
    )

    clear_informational_tags(
        assumed_role=assumed_role,
        resource_arns=[resource_arn],
    )

    logger.info(f"Deregistered resource: {resource_arn}")


def handle_asg_tagging_event(event: AsgRegistrationEvent) -> Dict[str, Any]:
    """Handle ASG CloudTrail tagging events."""

    # ASG tagging events are limited to just create/delete events from CloudTrail. Unfortunately
    # a tag update is reported as a delete event immediately followed by a create event, and when
    # an ASG is created with a schedule tag already existing on it, no tag create/delete event is sent
    # to CloudTrail.
    # this means that our most reliable way to ensure that ASGs are correctly registered/deregistered is to
    # describe them in response to every event and rely on tags present on the describe call.

    logger.append_keys(
        context=LogContext.REGISTRATION.value,
        account=event.account,
        region=event.region,
        service="autoscaling",
    )

    assumed_role = assume_role(
        account=event.account,
        region=event.region,
        role_name=env.scheduler_role_name,
    )

    for asg_event in event.detail.requestParameters.tags:
        if asg_event.key != env.schedule_tag_key:
            continue  # ignore updates to non-schedule tags

        logger.append_keys(
            instance=asg_event.resourceId,
        )

        for asg in AsgService.describe_asgs(assumed_role, [asg_event.resourceId]):
            # the event could be a create or delete event, so we need to check if the ASG has a schedule tag
            if asg.tags.get(env.schedule_tag_key):
                # create event
                register_asg_resources([asg], assumed_role, env)
            else:
                # delete event
                registry_record = cast(
                    Optional[RegisteredAsgInstance],
                    registry.get(RegistryKey.from_arn(asg.arn)),
                )
                # it's very possible that we have already deleted the resource, so don't error if the record does not exist
                if registry_record:
                    deregister_asg_resources([registry_record], assumed_role, env)

    return {"statusCode": 200, "body": "ASG resources processed successfully"}
