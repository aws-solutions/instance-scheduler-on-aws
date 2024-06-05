# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from dataclasses import dataclass
from typing import TYPE_CHECKING

from instance_scheduler.service.abstract_instance import AbstractInstance

if TYPE_CHECKING:
    from mypy_boto3_ec2.literals import InstanceStateNameType, InstanceTypeType
else:
    InstanceStateNameType = object
    InstanceTypeType = object


@dataclass(kw_only=True)
class EC2Instance(AbstractInstance):
    _current_state: InstanceStateNameType
    _instance_type: InstanceTypeType

    @property
    def display_str(self) -> str:
        s = f"EC2:{self.id}"
        if self.name:
            s += " ({})".format(self.name)
        return s

    @property
    def is_schedulable(self) -> bool:
        return self.current_state in ["running", "stopped"]

    @property
    def is_running(self) -> bool:
        return self.current_state == "running"

    @property
    def is_stopped(self) -> bool:
        return self.current_state == "stopped"

    @property
    def is_resizable(self) -> bool:
        return True
