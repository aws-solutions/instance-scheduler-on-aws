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
from instance_scheduler.util.session_manager import AssumedRole, assume_role
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
    # CloudTrail only includes the fields the caller sent, and the shape varies by
    # event. CreateOrUpdateTags/DeleteTags include resourceId/resourceType, but
    # CreateAutoScalingGroup tag entries may omit them (the group name is carried in
    # requestParameters.autoScalingGroupName instead). CreateOrUpdateTags may omit
    # PropagateAtLaunch, and DeleteTags sends neither value nor propagateAtLaunch.
    # Absent fields are represented as None; the handler decides register vs.
    # deregister from the live DescribeAutoScalingGroups tags, not these fields.
    key: str
    resourceId: Optional[str] = None
    resourceType: Optional[str] = None
    value: Optional[str] = None
    propagateAtLaunch: Optional[bool] = None


class RegistrationFailureException(Exception):
    pass


class AsgRequestParameters(BaseModel):
    tags: List[AsgTag] = []
    # present on CreateAutoScalingGroup: the name of the group created with tags
    autoScalingGroupName: Optional[str] = None


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
    if event.detail.resource_type not in ["instance"]:
        logger.debug(
            f"event for unsupported ec2 resource_type. skipping...: {event.detail.resource_type}"
        )
        return True  # skip

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


def _reconcile_asg(assumed_role: AssumedRole, asg_name: str) -> None:
    """Describe the named ASG and register or deregister it from its live tags.

    The decision is made from the live DescribeAutoScalingGroups tags rather than
    the event payload, so create, tag-update, and delete events all converge to the
    correct state regardless of event type or ordering.
    """
    for asg in AsgService.describe_asgs(assumed_role, [asg_name]):
        if asg.tags.get(env.schedule_tag_key):
            register_asg_resources([asg], assumed_role, env)
        else:
            registry_record = cast(
                Optional[RegisteredAsgInstance],
                registry.get(RegistryKey.from_arn(asg.arn)),
            )
            # the resource may already be deregistered; don't error if it's missing
            if registry_record:
                deregister_asg_resources([registry_record], assumed_role, env)


def handle_asg_tagging_event(event: AsgRegistrationEvent) -> Dict[str, Any]:
    """Handle ASG CloudTrail events (tagging and creation).

    ASGs are onboarded from three CloudTrail events: CreateOrUpdateTags and
    DeleteTags (tag add/change/remove on an existing group) and
    CreateAutoScalingGroup (a group created with the schedule tag already present,
    which emits no separate tagging event). A tag update also arrives as a
    DeleteTags immediately followed by a CreateOrUpdateTags. In every case we
    describe the group and rely on its live tags rather than the event payload, so
    the outcome is correct regardless of event type or ordering.
    """
    detail = event.detail
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

    if detail.eventName == "CreateAutoScalingGroup":
        # A group created with the schedule tag already on it. The group name is in
        # requestParameters.autoScalingGroupName; tag entries may omit resourceId.
        # The EventBridge rule only forwards creates carrying the schedule tag key.
        asg_name = detail.requestParameters.autoScalingGroupName
        if asg_name:
            logger.append_keys(instance=asg_name)
            _reconcile_asg(assumed_role, asg_name)
        else:
            # The rule matched this create, so a missing group name is unexpected;
            # log it rather than silently dropping the event.
            logger.warning(
                "CreateAutoScalingGroup event has no autoScalingGroupName in "
                "requestParameters; skipping"
            )
    else:
        for asg_event in detail.requestParameters.tags:
            if asg_event.key != env.schedule_tag_key:
                continue  # ignore updates to non-schedule tags
            if not asg_event.resourceId:
                continue  # tag entry without a resource id cannot be located
            logger.append_keys(instance=asg_event.resourceId)
            _reconcile_asg(assumed_role, asg_event.resourceId)

    return {"statusCode": 200, "body": "ASG resources processed successfully"}
