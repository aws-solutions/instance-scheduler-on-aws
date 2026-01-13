# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import batched
from typing import Any, Iterable, Optional, Self, Union

from instance_scheduler.observability.powertools_logging import powertools_logger
from instance_scheduler.observability.tag_keys import (
    InformationalTagKey,
)
from instance_scheduler.scheduling.scheduling_decision import (
    ManagedInstance,
    RuntimeInfo,
)
from instance_scheduler.scheduling.scheduling_result import (
    SchedulingAction,
    SchedulingResult,
)
from instance_scheduler.util.arn import ARN
from instance_scheduler.util.session_manager import AssumedRole

logger = powertools_logger()


@dataclass(frozen=True)
class TagWriteRequest:
    tags: tuple[tuple[str, str], ...]

    def __init__(self, tags: dict[str, str]) -> None:
        object.__setattr__(self, "tags", tuple(sorted(tags.items())))

    def execute(self, assumed_role: AssumedRole, arns: list[str]) -> None:
        try:
            tagging = assumed_role.client("resourcegroupstaggingapi")
            for batch in batched(arns, 20):
                tagging.tag_resources(ResourceARNList=batch, Tags=dict(self.tags))
        except Exception as e:
            # Log error but don't raise to prevent blocking other operations
            logger.error(f"Failed to apply tags to resources {arns}: {e}")
            raise


@dataclass(frozen=True)
class TagDeleteRequest:
    tag_keys: tuple[str, ...]

    def __init__(self, tag_keys: list[str]) -> None:
        object.__setattr__(self, "tag_keys", tuple(sorted(tag_keys)))

    def execute(self, assumed_role: AssumedRole, arns: list[str]) -> None:
        try:
            tagging = assumed_role.client("resourcegroupstaggingapi")
            for batch in batched(arns, 20):
                tagging.untag_resources(
                    ResourceARNList=batch, TagKeys=list(self.tag_keys)
                )
        except Exception as e:
            # Log error but don't raise to prevent blocking other operations
            logger.error(f"Failed to remove tags from resources {arns}: {e}")
            raise


class InfoTaggingContext:
    BUFFER_MAX_LENGTH = 20
    hub_stack_arn: str

    def __init__(self, assumed_role: AssumedRole, hub_stack_arn: str) -> None:
        self.buffers: dict[Union[TagWriteRequest, TagDeleteRequest], list[str]] = (
            defaultdict(list)
        )
        self.assumed_role = assumed_role
        self.hub_stack_arn = hub_stack_arn

    def __enter__(self) -> Self:
        return self

    def __exit__(self, _exc_type: Any, _exc_val: Any, _exc_tb: Any) -> None:
        self.flush()

    def push(
        self, resource_arn: ARN, request: Union[TagWriteRequest, TagDeleteRequest]
    ) -> None:
        self.buffers[request].append(str(resource_arn))
        if len(self.buffers[request]) >= self.BUFFER_MAX_LENGTH:
            try:
                request.execute(self.assumed_role, self.buffers[request])
                del self.buffers[request]
            except Exception:
                # Keep buffer intact on failure for potential retry
                pass

    def flush(self) -> None:
        for request, arns in self.buffers.items():
            try:
                request.execute(self.assumed_role, arns)
            except Exception:
                pass
        self.buffers.clear()

    def push_info_tag_update(
        self,
        resources: Iterable[RuntimeInfo],
        last_action: Optional[str] = None,
        error_code: Optional[str] = None,
        error_message: Optional[str] = None,
        additional_tags: Optional[dict[str, str]] = None,
    ) -> None:

        for resource in resources:
            if InformationalTagKey.ERROR in resource.tags:
                self.push(
                    resource.arn,
                    TagDeleteRequest(
                        [
                            InformationalTagKey.ERROR.value,
                            InformationalTagKey.ERROR_MESSAGE.value,
                        ]
                    ),
                )

            self.push(
                resource.arn,
                TagWriteRequest(
                    {
                        k: v[:256]
                        for k, v in {
                            InformationalTagKey.MANAGED_BY.value: self.hub_stack_arn,
                            InformationalTagKey.ERROR.value: error_code,
                            InformationalTagKey.ERROR_MESSAGE.value: error_message,
                            InformationalTagKey.LAST_ACTION.value: last_action,
                            **(additional_tags or {}),
                        }.items()
                        if v is not None
                    }
                ),
            )

    def push_clear_info_tags(self, resource_arn: ARN) -> None:
        tag_keys = [tag.value for tag in InformationalTagKey]
        self.push(resource_arn, TagDeleteRequest(tag_keys))


def format_current_time() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def apply_informational_tags_for_results(
    assumed_role: AssumedRole,
    results: Iterable[SchedulingResult[ManagedInstance]],
    hub_stack_arn: str,
) -> None:
    with InfoTaggingContext(assumed_role, hub_stack_arn) as context:
        # calculate current time once to ensure tags all use the same time for batching
        current_time = format_current_time()

        for result in results:
            if result.error_code:
                context.push_info_tag_update(
                    [result.instance.runtime_info],
                    error_code=f"{result.error_code.value} ({current_time})",
                    error_message=result.error_message,
                )
            else:
                if (
                    result.action_taken
                    and result.action_taken != SchedulingAction.DO_NOTHING
                ):
                    context.push_info_tag_update(
                        [result.instance.runtime_info],
                        last_action=f"{result.action_taken.value} {current_time}",
                    )


def clear_informational_tags(
    assumed_role: AssumedRole, resource_arns: list[str]
) -> None:
    """Clear all informational tags from a resource using Resource Groups Tagging API."""
    tagging = assumed_role.client("resourcegroupstaggingapi")
    tag_keys = [tag.value for tag in InformationalTagKey]
    for batch in batched(resource_arns, 20):
        tagging.untag_resources(ResourceARNList=batch, TagKeys=tag_keys)
