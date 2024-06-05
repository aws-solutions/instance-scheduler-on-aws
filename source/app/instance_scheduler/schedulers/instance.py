# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from dataclasses import dataclass
from typing import Any, Literal, NotRequired, Optional, Sequence, TypedDict

from instance_scheduler.configuration.instance_schedule import InstanceSchedule


class Instance(TypedDict):
    id: str
    arn: NotRequired[str]
    allow_resize: bool
    hibernate: bool
    state: Any
    state_name: str
    is_running: bool
    is_terminated: bool
    current_state: Literal["running", "stopped"]
    instancetype: str
    engine_type: NotRequired[str]
    maintenance_window: Optional[Sequence[InstanceSchedule]]
    tags: dict[str, str]
    name: str
    schedule_name: str
    is_cluster: NotRequired[bool]
    resized: NotRequired[bool]
    account: NotRequired[str]
    region: NotRequired[str]
    service: NotRequired[str]
    instance_str: NotRequired[str]


@dataclass
class SchedulableInstance:
    id: str
    allow_resize: bool
    hibernate: bool
    state: Any
    state_name: str
    is_running: bool
    is_terminated: bool
    current_state: Literal["running", "stopped"]
    instancetype: str
    tags: dict[str, str]
    name: str
    schedule_name: str
    maintenance_window: Optional[Sequence[InstanceSchedule]] = None
    arn: Optional[str] = None
    is_cluster: Optional[bool] = None
    resized: Optional[bool] = None
    account: Optional[str] = None
    region: Optional[str] = None
    service: Optional[str] = None
    instance_str: Optional[str] = None
    engine_type: Optional[str] = None

    @classmethod
    def from_instance(cls, instance: Instance) -> "SchedulableInstance":
        return SchedulableInstance(
            id=instance["id"],
            allow_resize=instance["allow_resize"],
            hibernate=instance["hibernate"],
            state=instance["state"],
            state_name=instance["state_name"],
            is_running=instance["is_running"],
            is_terminated=instance["is_terminated"],
            current_state=instance["current_state"],
            instancetype=instance["instancetype"],
            tags=instance["tags"],
            name=instance["name"],
            schedule_name=instance["schedule_name"],
            maintenance_window=instance.get("maintenance_window"),
            arn=instance.get("arn"),
            is_cluster=instance.get("is_cluster"),
            resized=instance.get("resized"),
            account=instance.get("account"),
            region=instance.get("region"),
            service=instance.get("service"),
            instance_str=instance.get("instance_str"),
            engine_type=instance.get("engine_type"),
        )
