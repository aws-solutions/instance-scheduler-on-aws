# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mypy_boto3_autoscaling.type_defs import AutoScalingGroupTypeDef
else:
    AutoScalingGroupTypeDef = object
    NewSchedulingContext = object


class AsgTagValidationError(Exception):
    pass


@dataclass(frozen=True)
class AsgSize:
    min_size: int
    desired_size: int
    max_size: int

    def is_stopped_state(self) -> bool:
        return self.min_size == 0 and self.desired_size == 0 and self.max_size == 0

    def __str__(self) -> str:
        return f"{self.min_size}-{self.desired_size}-{self.max_size}"

    def to_mdm_str(self) -> str:
        return f"{self.min_size}-{self.desired_size}-{self.max_size}"

    @classmethod
    def from_mdm_str(cls, mdm_string: str) -> "AsgSize":
        try:
            min_size, desired_size, max_size = mdm_string.split("-")
            return cls(
                min_size=int(min_size),
                desired_size=int(desired_size),
                max_size=int(max_size),
            )
        except Exception:
            raise AsgTagValidationError("Unable to parse MDM tag value")

    @classmethod
    def from_group(cls, group: AutoScalingGroupTypeDef) -> "AsgSize":
        return cls(
            min_size=group["MinSize"],
            desired_size=group["DesiredCapacity"],
            max_size=group["MaxSize"],
        )

    @classmethod
    def stopped(cls) -> "AsgSize":
        return cls(min_size=0, desired_size=0, max_size=0)
