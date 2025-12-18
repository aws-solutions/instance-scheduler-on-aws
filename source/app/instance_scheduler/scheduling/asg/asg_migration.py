# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Final

from instance_scheduler.observability.powertools_logging import powertools_logger
from instance_scheduler.scheduling.asg.asg_runtime_info import (
    MDM_TAG_KEY,
    AsgRuntimeInfo,
)
from instance_scheduler.scheduling.asg.asg_scheduling_envionment import (
    AsgSchedulingEnvironment,
)
from instance_scheduler.scheduling.asg.asg_service import (
    AsgTagValidationError,
)
from instance_scheduler.scheduling.asg.asg_size import AsgSize
from instance_scheduler.util.session_manager import AssumedRole
from instance_scheduler.util.validation import (
    ValidationException,
    require_int,
    require_str,
)

logger = powertools_logger()


@dataclass(frozen=True)
# @deprecated("replaced by registry record and MDMTag, is used only for migration")
class AsgMetadataTag:
    schedule: str
    ttl: str
    min_size: int
    max_size: int
    desired_size: int

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
    def from_json(cls, json_str: str) -> "AsgMetadataTag":
        try:
            json_data: Final = json.loads(json_str)
        except Exception:
            raise AsgTagValidationError("Unable to parse Scheduled tag value")

        if not isinstance(json_data, dict):
            raise AsgTagValidationError("Invalid Scheduled tag value: not a dict")

        try:
            return AsgMetadataTag(
                schedule=require_str(json_data, "schedule"),
                ttl=require_str(json_data, "ttl"),
                min_size=require_int(json_data, "min_size"),
                max_size=require_int(json_data, "max_size"),
                desired_size=require_int(json_data, "desired_size"),
            )
        except ValidationException as e:
            raise AsgTagValidationError(f"Invalid Scheduled tag value: {e}") from e


def asg_needs_migration(asg: AsgRuntimeInfo, env: AsgSchedulingEnvironment) -> bool:
    return asg.tags.get(env.asg_metadata_tag_key) is not None


def migrate_asg(
    asg: AsgRuntimeInfo, assumed_role: AssumedRole, env: AsgSchedulingEnvironment
) -> None:
    """migrate asg to new version (v3.0.x -> v3.1.0)

    the purpose of this migration is to preserve the MDM value stored on the metadata tag of an ASG and is a best-effort migration.
    if the old metadata tag is corrupt or broken in some way, the function will simply quit silently and allow MDM values to
    be regenerated using the regular defaults.

    this function and rollback_migration are both idempotent and will silently quit if run on resources that do not need or have already been
    migrated.
    """
    raw_meta_tag = asg.tags.get(env.asg_metadata_tag_key)
    if raw_meta_tag is None:
        return  # no meta tag exists, nothing to migrate

    try:
        metadata_tag = AsgMetadataTag.from_json(raw_meta_tag)
        asg_size = AsgSize(
            min_size=metadata_tag.min_size,
            desired_size=metadata_tag.desired_size,
            max_size=metadata_tag.max_size,
        )
    except AsgTagValidationError:
        return  # tag is corrupt, quit silently

    asg_client = assumed_role.client("autoscaling")

    asg_client.create_or_update_tags(
        Tags=[
            {
                "ResourceType": "auto-scaling-group",
                "ResourceId": asg.resource_id,
                "Key": MDM_TAG_KEY,
                "Value": asg_size.to_mdm_str(),
                "PropagateAtLaunch": False,
            }
        ]
    )

    asg_client.delete_tags(
        Tags=[
            {
                "ResourceType": "auto-scaling-group",
                "ResourceId": asg.resource_id,
                "Key": env.asg_metadata_tag_key,
            }
        ]
    )
    logger.info(f"Migrated {asg.arn} to use MDM tag")


def rollback_asg_migration(
    asg: AsgRuntimeInfo, assumed_role: AssumedRole, env: AsgSchedulingEnvironment
) -> None:
    """rollback migration (v3.1.0 -> v3.0.x)
    this function and migrate_asg are both idempotent and will silently quit if run on resources that do not need or have already been
    migrated.
    """
    mdm_str = asg.tags.get(MDM_TAG_KEY)

    if not mdm_str:
        # the purpose of this rollback is to ensure that MDM values are not reset. if there is no MDM string on the instance,
        # then there is nothing to rollback as v3.0.x will use the current size for the new MDM value (exactly the same as we would do here)
        return

    asg_size = AsgSize.from_mdm_str(mdm_str)
    metadata_tag = AsgMetadataTag(
        schedule="migration-rolled-back",  # this and the TTL being different will force v3.0.x to reconfigure the schedule on the next cycle
        ttl=datetime.now(timezone.utc).isoformat(),
        min_size=asg_size.min_size,
        max_size=asg_size.max_size,
        desired_size=asg_size.desired_size,
    )

    asg_client = assumed_role.client("autoscaling")

    asg_client.create_or_update_tags(
        Tags=[
            {
                "ResourceType": "auto-scaling-group",
                "ResourceId": asg.resource_id,
                "Key": env.asg_metadata_tag_key,
                "Value": metadata_tag.to_json(),
                "PropagateAtLaunch": False,
            }
        ]
    )

    asg_client.delete_tags(
        Tags=[
            {
                "ResourceType": "auto-scaling-group",
                "ResourceId": asg.resource_id,
                "Key": MDM_TAG_KEY,
            }
        ]
    )

    logger.info(f"rolled back {asg.arn} to use metadata tag")
