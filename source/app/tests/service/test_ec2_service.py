# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from collections.abc import Sequence
from dataclasses import dataclass, replace
from itertools import chain
from typing import TYPE_CHECKING, Final
from unittest.mock import MagicMock, patch

import boto3
from boto3.session import Session

from instance_scheduler import ScheduleState
from instance_scheduler.configuration.instance_schedule import (
    Instance,
    InstanceSchedule,
)
from instance_scheduler.service import Ec2Service, ServiceArgs
from instance_scheduler.service.ec2 import EC2StateCode, get_tags
from tests import ami
from tests.integration.helpers.schedule_helpers import quick_time
from tests.integration.helpers.scheduling_context_builder import build_context
from tests.logger import MockLogger

if TYPE_CHECKING:
    from mypy_boto3_ec2.client import EC2Client
    from mypy_boto3_ec2.literals import InstanceStateNameType, InstanceTypeType
    from mypy_boto3_ec2.type_defs import InstanceTypeDef, TagTypeDef
else:
    EC2Client = object
    InstanceStateNameType = object
    InstanceTypeType = object
    InstanceTypeDef = object
    TagTypeDef = object


def test_ec2_state_code() -> None:
    assert EC2StateCode.PENDING.value == 0
    assert EC2StateCode.RUNNING.value == 16
    assert EC2StateCode.SHUTTING_DOWN.value == 32
    assert EC2StateCode.TERMINATED.value == 48
    assert EC2StateCode.STOPPING.value == 64
    assert EC2StateCode.STOPPED.value == 80


def test_get_tags() -> None:
    assert get_tags({}) == {}

    instance: Final[InstanceTypeDef] = {
        "Tags": [
            {"Key": "foo", "Value": "bar"},
            {"Key": "baz", "Value": "qux"},
        ]
    }

    assert get_tags(instance) == {"foo": "bar", "baz": "qux"}


def mock_service_args() -> ServiceArgs:
    return ServiceArgs(
        account_id="111111111111",
        scheduling_context=build_context(quick_time(0, 0, 0)),
        logger=MockLogger(),
        session=Session(),
        stack_name="",
    )


def test_ec2_service_attributes() -> None:
    service = Ec2Service(mock_service_args())

    assert service.service_name == "ec2"
    assert service.allow_resize


@dataclass(frozen=True)
class InstancesOfStatus:
    qty: int
    all_ids: Sequence[str]
    running_ids: Sequence[str]
    stopped_ids: Sequence[str]
    terminated_ids: Sequence[str]


def create_instances_of_status(
    ec2: EC2Client,
    *,
    instance_type: InstanceTypeType,
    qty_running: int = 0,
    qty_stopped: int = 0,
    qty_terminated: int = 0,
) -> InstancesOfStatus:
    total_qty: Final = qty_running + qty_stopped + qty_terminated
    run_response = ec2.run_instances(
        ImageId=ami, InstanceType=instance_type, MinCount=total_qty, MaxCount=total_qty
    )
    instance_ids = [instance["InstanceId"] for instance in run_response["Instances"]]
    assert (
        len(instance_ids) == total_qty
    ), "Failed to create the right number of instances"

    running_ids = instance_ids[0:qty_running]
    stopped_ids = instance_ids[qty_running : qty_running + qty_stopped]
    terminated_ids = instance_ids[qty_running + qty_stopped :]

    ec2.get_waiter("instance_running").wait(InstanceIds=instance_ids)

    ec2.stop_instances(InstanceIds=stopped_ids)
    if terminated_ids:
        ec2.terminate_instances(InstanceIds=terminated_ids)

    if stopped_ids:
        ec2.get_waiter("instance_stopped").wait(InstanceIds=stopped_ids)
    if terminated_ids:
        ec2.get_waiter("instance_terminated").wait(InstanceIds=terminated_ids)

    return InstancesOfStatus(
        qty=total_qty,
        all_ids=instance_ids,
        running_ids=running_ids,
        stopped_ids=stopped_ids,
        terminated_ids=terminated_ids,
    )


@patch("instance_scheduler.service.ec2.EC2SSMMaintenanceWindows")
def test_get_schedulable_instances(mock_mw: MagicMock, moto_ec2: None) -> None:
    service_args = mock_service_args()
    service_args["scheduling_context"] = replace(
        service_args["scheduling_context"], enable_ssm_maintenance_windows=True
    )
    service: Final = Ec2Service(service_args)
    assert service.get_schedulable_instances() == []

    ec2: Final[EC2Client] = boto3.client("ec2")
    instance_type: Final[InstanceTypeType] = "m6g.medium"
    instances = create_instances_of_status(
        ec2, instance_type=instance_type, qty_running=6, qty_stopped=2, qty_terminated=2
    )

    hibernated_instance_ids: Final = instances.running_ids[0:2]
    untagged_instance_ids: Final = instances.running_ids[2:4]

    schedule_tag_key = service_args["scheduling_context"].tag_name
    for instance_id in instances.all_ids:
        schedule_name = f"{instance_id}-schedule"
        hibernate = instance_id in hibernated_instance_ids
        service_args["scheduling_context"].schedules[schedule_name] = InstanceSchedule(
            schedule_name, hibernate=hibernate
        )
        tags: list[TagTypeDef] = [
            {"Key": "Name", "Value": f"{instance_id}-name"},
        ]
        if instance_id not in untagged_instance_ids:
            tags.append({"Key": schedule_tag_key, "Value": schedule_name})
        ec2.create_tags(Resources=[instance_id], Tags=tags)

    instance_with_maintenance_window = instances.running_ids[0]
    schedule_name = f"{instance_with_maintenance_window}-schedule"
    maintenance_window_name = f"{instance_with_maintenance_window}-mw"
    service_args["scheduling_context"].schedules[
        schedule_name
    ].use_maintenance_window = True
    service_args["scheduling_context"].schedules[
        schedule_name
    ].ssm_maintenance_window = maintenance_window_name
    maintenance_window_schedule = InstanceSchedule(maintenance_window_name)
    mock_mw.return_value.ssm_maintenance_windows.return_value = {
        maintenance_window_name: maintenance_window_schedule
    }

    result = service.get_schedulable_instances()

    assert len(result) == instances.qty - len(untagged_instance_ids) - len(
        instances.terminated_ids
    )

    schedulable_instances = {instance["id"]: instance for instance in result}

    for instance_id, instance in schedulable_instances.items():
        assert instance["id"] == instance_id
        assert "arn" not in instance
        assert instance["allow_resize"]
        name = f"{instance_id}-name"
        assert instance["name"] == name
        assert instance["instancetype"] == instance_type
        assert "engine_type" not in instance
        schedule_name = f"{instance_id}-schedule"
        assert instance["schedule_name"] == schedule_name
        assert instance["tags"] == {schedule_tag_key: schedule_name, "Name": name}
        assert not instance["resized"]
        assert "is_cluster" not in instance
        assert "account" not in instance
        assert "region" not in instance
        assert "service" not in instance
        assert "instance_str" not in instance

        if instance_id != instance_with_maintenance_window:
            assert instance["maintenance_window"] is None

    for instance_id in instances.running_ids:
        if instance_id not in untagged_instance_ids:
            instance = schedulable_instances[instance_id]
            assert instance["state"] == EC2StateCode.RUNNING
            assert instance["state_name"] == "running"
            assert instance["is_running"]
            assert not instance["is_terminated"]
            assert instance["current_state"] == "running"

            assert instance["hibernate"] == bool(instance_id in hibernated_instance_ids)

    assert (
        schedulable_instances[instance_with_maintenance_window]["maintenance_window"]
        is maintenance_window_schedule
    )

    for instance_id in instances.stopped_ids:
        instance = schedulable_instances[instance_id]
        assert instance["state"] == EC2StateCode.STOPPED
        assert instance["state_name"] == "stopped"
        assert not instance["is_running"]
        assert not instance["is_terminated"]
        assert instance["current_state"] == "stopped"
        assert not instance["hibernate"]

    for instance_id in chain(instances.terminated_ids, untagged_instance_ids):
        assert instance_id not in schedulable_instances


def instance_data_from(
    *,
    instance_id: str,
    instance_state: InstanceStateNameType,
    instance_type: InstanceTypeType,
) -> Instance:
    if instance_state not in {"running", "stopped"}:
        raise ValueError(f"Unimplemented instance data conversion: {instance_state}")
    running: Final = instance_state == "running"
    state_code: Final = EC2StateCode.RUNNING if running else EC2StateCode.STOPPED
    schedule_state: Final[ScheduleState] = "running" if running else "stopped"
    return Instance(
        id=instance_id,
        allow_resize=True,
        hibernate=False,
        state=state_code,
        state_name=instance_state,
        is_running=running,
        is_terminated=False,
        current_state=schedule_state,
        instancetype=instance_type,
        maintenance_window=None,
        tags={},
        name="",
        schedule_name=None,
    )


def test_resize_instance(moto_ec2: None) -> None:
    ec2: Final[EC2Client] = boto3.client("ec2")
    instance_type: Final[InstanceTypeType] = "m6g.medium"
    instances = create_instances_of_status(
        ec2, instance_type=instance_type, qty_running=1
    )

    instance_id = instances.all_ids[0]
    instance = instance_data_from(
        instance_id=instance_id, instance_state="running", instance_type=instance_type
    )
    new_instance_type: Final[InstanceTypeType] = "m6g.12xlarge"

    service: Final = Ec2Service(mock_service_args())
    service.resize_instance(instance, new_instance_type)

    assert (
        ec2.describe_instances(InstanceIds=[instance_id])["Reservations"][0][
            "Instances"
        ][0]["InstanceType"]
        == new_instance_type
    )


def test_start_instances(moto_ec2: None) -> None:
    ec2: Final[EC2Client] = boto3.client("ec2")
    instance_type: Final[InstanceTypeType] = "m6g.xlarge"
    instances = create_instances_of_status(
        ec2, instance_type=instance_type, qty_stopped=7
    )

    service: Final = Ec2Service(mock_service_args())
    assert list(service.start_instances([])) == []

    instances_to_start: list[Instance] = []
    for instance_id in instances.stopped_ids:
        instances_to_start.append(
            instance_data_from(
                instance_id=instance_id,
                instance_state="stopped",
                instance_type=instance_type,
            )
        )

    result = list(service.start_instances(instances_to_start))
    instance_results: Final = {instance_id: status for (instance_id, status) in result}

    for instance_id in instances.stopped_ids:
        assert instance_results[instance_id] == "running"

    ec2.get_waiter("instance_running").wait(InstanceIds=instances.stopped_ids)

    statuses = ec2.describe_instance_status(InstanceIds=instances.stopped_ids)
    for status in statuses["InstanceStatuses"]:
        assert status["InstanceState"]["Name"] == "running"


def test_start_instances_with_errors(moto_ec2: None) -> None:
    ec2: Final[EC2Client] = boto3.client("ec2")
    instance_type: Final[InstanceTypeType] = "m6g.xlarge"
    instances = create_instances_of_status(
        ec2, instance_type=instance_type, qty_stopped=100
    )

    service: Final = Ec2Service(mock_service_args())

    instances_to_start: list[Instance] = []
    for instance_id in instances.stopped_ids:
        instances_to_start.append(
            instance_data_from(
                instance_id=instance_id,
                instance_state="stopped",
                instance_type=instance_type,
            )
        )
        # add a duplicate Instance with a bad identifier, interleaved
        bad_instance_id = "id-bad" + instance_id[6:]
        instances_to_start.append(
            instance_data_from(
                instance_id=bad_instance_id,
                instance_state="stopped",
                instance_type=instance_type,
            )
        )

    result = list(service.start_instances(instances_to_start))
    instance_results: Final = {instance_id: status for (instance_id, status) in result}

    for instance_id in instances.stopped_ids:
        assert instance_results[instance_id] == "running"

    ec2.get_waiter("instance_running").wait(InstanceIds=instances.stopped_ids)

    statuses = ec2.describe_instance_status(InstanceIds=instances.stopped_ids)
    for status in statuses["InstanceStatuses"]:
        assert status["InstanceState"]["Name"] == "running"


def test_stop_instances(moto_ec2: None) -> None:
    ec2: Final[EC2Client] = boto3.client("ec2")
    instance_type: Final[InstanceTypeType] = "m6g.large"
    instances = create_instances_of_status(
        ec2, instance_type=instance_type, qty_running=52
    )

    service: Final = Ec2Service(mock_service_args())
    assert list(service.stop_instances([])) == []

    instances_to_stop: list[Instance] = []
    for instance_id in instances.running_ids:
        instances_to_stop.append(
            instance_data_from(
                instance_id=instance_id,
                instance_state="running",
                instance_type=instance_type,
            )
        )

    result = list(service.stop_instances(instances_to_stop))
    instance_results: Final = {instance_id: status for (instance_id, status) in result}

    for instance_id in instances.running_ids:
        assert instance_results[instance_id] == "stopped"

    ec2.get_waiter("instance_stopped").wait(InstanceIds=instances.running_ids)

    statuses = ec2.describe_instance_status(InstanceIds=instances.running_ids)
    for status in statuses["InstanceStatuses"]:
        assert status["InstanceState"]["Name"] == "stopped"


def test_stop_instances_with_errors(moto_ec2: None) -> None:
    ec2: Final[EC2Client] = boto3.client("ec2")
    instance_type: Final[InstanceTypeType] = "m6g.large"
    instances = create_instances_of_status(
        ec2, instance_type=instance_type, qty_running=52
    )

    service: Final = Ec2Service(mock_service_args())

    instances_to_stop: list[Instance] = []
    for instance_id in instances.running_ids:
        instances_to_stop.append(
            instance_data_from(
                instance_id=instance_id,
                instance_state="stopped",
                instance_type=instance_type,
            )
        )
    # add a duplicate Instance with a bad identifier, after good instances
    for instance_id in instances.running_ids:
        bad_instance_id = "id-bad" + instance_id[6:]
        instances_to_stop.append(
            instance_data_from(
                instance_id=bad_instance_id,
                instance_state="stopped",
                instance_type=instance_type,
            )
        )

    result = list(service.stop_instances(instances_to_stop))
    instance_results: Final = {instance_id: status for (instance_id, status) in result}

    for instance_id in instances.running_ids:
        assert instance_results[instance_id] == "stopped"

    ec2.get_waiter("instance_stopped").wait(InstanceIds=instances.running_ids)

    statuses = ec2.describe_instance_status(InstanceIds=instances.running_ids)
    for status in statuses["InstanceStatuses"]:
        assert status["InstanceState"]["Name"] == "stopped"
