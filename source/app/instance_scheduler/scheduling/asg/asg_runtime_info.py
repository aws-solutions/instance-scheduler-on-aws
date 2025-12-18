# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from instance_scheduler.scheduling.asg.asg_size import AsgSize
from instance_scheduler.scheduling.scheduling_decision import RuntimeInfo
from instance_scheduler.util.arn import ARN

if TYPE_CHECKING:
    from mypy_boto3_autoscaling.type_defs import AutoScalingGroupTypeDef
else:
    AutoScalingGroupTypeDef = object

MDM_TAG_KEY = "IS-MinDesiredMax"


@dataclass
class AsgRuntimeInfo(RuntimeInfo):
    group: AutoScalingGroupTypeDef
    arn: ARN = None  # type: ignore # NOSONAR # will be set in post_init
    tags: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.tags = {tag["Key"]: tag["Value"] for tag in self.group.get("Tags", [])}
        self.arn = ARN(self.group.get("AutoScalingGroupARN", ""))

    @property
    def is_in_schedulable_state(self) -> bool:
        return True

    @property
    def is_running(self) -> bool:
        return not self.current_asg_size.is_stopped_state()

    @property
    def is_stopped(self) -> bool:
        return self.current_asg_size.is_stopped_state()

    # size property used for observability dashboard, not the same as MDM size
    @property
    def size(self) -> str:
        return "asg"

    @property
    def resource_id(self) -> str:
        return self.group["AutoScalingGroupName"]

    @property
    def current_asg_size(self) -> AsgSize:
        return AsgSize.from_group(self.group)

    @property
    def requested_asg_size(self) -> Optional[AsgSize]:
        mdm_tag = self.tags.get(MDM_TAG_KEY)
        return AsgSize.from_mdm_str(mdm_tag) if mdm_tag else None
