# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import random
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import chain
from typing import TYPE_CHECKING, Final
from unittest.mock import ANY, MagicMock, patch
from zoneinfo import ZoneInfo

import boto3
from boto3.session import Session
from botocore.stub import Stubber

from instance_scheduler.configuration.instance_schedule import InstanceSchedule
from instance_scheduler.configuration.scheduling_context import SchedulingContext
from instance_scheduler.handler.environments.scheduling_request_environment import (
    SchedulingRequestEnvironment,
)
from instance_scheduler.maint_win.ssm_mw_client import SSMMWClient
from instance_scheduler.model import EC2SSMMaintenanceWindow, MWStore
from instance_scheduler.service import Ec2Service
from instance_scheduler.service.ec2 import EC2StateCode, get_tags
from instance_scheduler.service.ec2_instance import EC2Instance
from instance_scheduler.util.session_manager import AssumedRole
from tests.conftest import get_ami
from tests.integration.helpers.schedule_helpers import quick_time
from tests.integration.helpers.scheduling_context_builder import (
    build_scheduling_context,
)
from tests.logger import MockLogger
from tests.test_utils.mock_scheduling_request_environment import (
    MockSchedulingRequestEnvironment,
)

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


def test_get_tags() -> None:
    assert get_tags({}) == {}

    instance: Final[InstanceTypeDef] = {
        "Tags": [
            {"Key": "foo", "Value": "bar"},
            {"Key": "baz", "Value": "qux"},
        ]
    }

    assert get_tags(instance) == {"foo": "bar", "baz": "qux"}


def build_ec2_service(
    env: SchedulingRequestEnvironment = MockSchedulingRequestEnvironment(),
    scheduling_context: SchedulingContext = build_scheduling_context(
        quick_time(0, 0, 0)
    ),
) -> Ec2Service:
    return Ec2Service(
        assumed_scheduling_role=AssumedRole(
            account="123456789012",
            region="us-east-1",
            role_name="role-name",
            session=Session(),
        ),
        scheduling_context=scheduling_context,
        logger=MockLogger(),
        env=env,
    )


def test_ec2_service_attributes() -> None:
    service = build_ec2_service()

    assert service.service_name == "ec2"


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
        ImageId=get_ami(),
        InstanceType=instance_type,
        MinCount=total_qty,
        MaxCount=total_qty,
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


@patch.object(SSMMWClient, "get_mws_from_ssm")
def test_get_schedulable_instances(
    mock_mw_backend: MagicMock,
    moto_backend: None,
    mw_store: MWStore,
) -> None:
    env = MockSchedulingRequestEnvironment(enable_ec2_ssm_maintenance_windows=True)
    service = build_ec2_service(env=env)
    assert list(service.describe_tagged_instances()) == []

    ec2: Final[EC2Client] = boto3.client("ec2")
    instance_type: Final[InstanceTypeType] = "m6g.medium"
    instances = create_instances_of_status(
        ec2, instance_type=instance_type, qty_running=6, qty_stopped=2, qty_terminated=2
    )

    hibernated_instance_ids: Final = instances.running_ids[0:2]
    untagged_instance_ids: Final = instances.running_ids[2:4]

    schedules: dict[str, InstanceSchedule] = dict()
    # setup schedules
    schedule_tag_key = env.schedule_tag_key
    for instance_id in instances.all_ids:
        schedule_name = f"{instance_id}-schedule"
        hibernate = instance_id in hibernated_instance_ids
        schedules[schedule_name] = InstanceSchedule(
            schedule_name,
            hibernate=hibernate,
            timezone=ZoneInfo("UTC"),
        )

        tags: list[TagTypeDef] = [
            {"Key": "Name", "Value": f"{instance_id}-name"},
        ]
        if instance_id not in untagged_instance_ids:
            tags.append({"Key": schedule_tag_key, "Value": schedule_name})
        ec2.create_tags(Resources=[instance_id], Tags=tags)

    # create schedules
    instance_with_maintenance_window = instances.running_ids[0]

    maintenance_window = EC2SSMMaintenanceWindow(
        window_name=f"{instance_with_maintenance_window}-mw",
        window_id="mw-00000000000000000",
        account_id="123456789012",
        region="us-east-1",
        schedule_timezone=ZoneInfo("UTC"),
        next_execution_time=quick_time(10, 20, 0),
        duration_hours=1,
    )
    schedule_name = f"{instance_with_maintenance_window}-schedule"
    schedules[schedule_name].ssm_maintenance_window = [maintenance_window.window_name]

    mock_mw_backend.return_value = [maintenance_window]

    service = build_ec2_service(
        env,
        build_scheduling_context(current_dt=quick_time(10, 0, 0), schedules=schedules),
    )
    result = list(service.describe_tagged_instances())

    assert len(result) == instances.qty - len(untagged_instance_ids) - len(
        instances.terminated_ids
    )

    schedulable_instances = {instance.id: instance for instance in result}

    for instance_id, instance in schedulable_instances.items():
        assert instance.id == instance_id
        assert instance.is_resizable
        name = f"{instance.id}-name"
        assert instance.name == name
        assert instance.instance_type == instance_type
        schedule_name = f"{instance.id}-schedule"
        assert instance.schedule_name == schedule_name
        assert instance.tags == {schedule_tag_key: schedule_name, "Name": name}
        assert not instance.resized

        if instance_id != instance_with_maintenance_window:
            assert instance.maintenance_windows == []

    for instance_id in instances.running_ids:
        if instance_id not in untagged_instance_ids:
            instance = schedulable_instances[instance_id]
            assert instance.current_state == "running"
            assert instance.is_running
            assert not instance.is_stopped

    assert schedulable_instances[
        instance_with_maintenance_window
    ].maintenance_windows == [
        maintenance_window.to_schedule(env.scheduler_frequency_minutes)
    ]

    for instance_id in instances.stopped_ids:
        instance = schedulable_instances[instance_id]
        assert not instance.is_running
        assert instance.is_stopped
        assert instance.current_state == "stopped"
        assert not instance.should_hibernate

    for instance_id in chain(instances.terminated_ids, untagged_instance_ids):
        assert instance_id not in schedulable_instances


def test_get_schedulable_instances_omits_asg_instances(moto_backend: None) -> None:
    env: Final = MockSchedulingRequestEnvironment()
    service: Final = build_ec2_service(env=env)

    ec2: Final[EC2Client] = boto3.client("ec2")
    instance_type: Final[InstanceTypeType] = "m6g.12xlarge"
    instances = create_instances_of_status(
        ec2, instance_type=instance_type, qty_running=1
    )

    tags: list[TagTypeDef] = [
        {"Key": env.schedule_tag_key, "Value": "my-schedule"},
        {"Key": "aws:autoscaling:groupName", "Value": "my-group"},
    ]
    ec2.create_tags(Resources=[instances.all_ids[0]], Tags=tags)

    assert list(service.describe_tagged_instances()) == []


@patch.object(SSMMWClient, "get_mws_from_ssm")
def test_describe_tagged_instances_omits_mw_with_no_next_execution_time(
    mock_mw_backend: MagicMock,
    moto_backend: None,
    mw_store: MWStore,
) -> None:
    env = MockSchedulingRequestEnvironment(enable_ec2_ssm_maintenance_windows=True)
    service = build_ec2_service(env=env)

    assert list(service.describe_tagged_instances()) == []

    # create instance
    ec2: Final[EC2Client] = boto3.client("ec2")
    instance_type: Final[InstanceTypeType] = "m6g.12xlarge"
    instances = create_instances_of_status(
        ec2, instance_type=instance_type, qty_running=1
    )
    instance_id = instances.all_ids[0]
    schedule_name = f"{instance_id}-schedule"
    tags: list[TagTypeDef] = [
        {"Key": "Name", "Value": f"{instance_id}-name"},
        {"Key": env.schedule_tag_key, "Value": schedule_name},
    ]
    ec2.create_tags(Resources=[instance_id], Tags=tags)

    # mw that has next_execution_time and will be processed
    maintenance_window = EC2SSMMaintenanceWindow(
        window_name=f"{instance_id}-mw",
        window_id="mw-00000000000000000",
        account_id="123456789012",
        region="us-east-1",
        schedule_timezone=ZoneInfo("UTC"),
        next_execution_time=quick_time(10, 20, 0),
        duration_hours=1,
    )

    # mw that does not have next_execution_time and will be filtered out
    maintenance_window_no_next_execution_time = EC2SSMMaintenanceWindow(
        window_name=f"{instance_id}-mw-no-next-execution-time",
        window_id="mw-00000000000000001",
        account_id="123456789012",
        region="us-east-1",
        schedule_timezone=ZoneInfo("UTC"),
        next_execution_time=None,
        duration_hours=1,
    )

    # create schedule using both maintenance windows, maintenance_window_no_next_execution_time should be ignored
    schedules: dict[str, InstanceSchedule] = dict()
    schedules[schedule_name] = InstanceSchedule(
        schedule_name,
        timezone=ZoneInfo("UTC"),
        ssm_maintenance_window=[
            maintenance_window.window_name,
            maintenance_window_no_next_execution_time.window_name,
        ],
    )

    # mw returned by SSMMWClient
    mock_mw_backend.return_value = [
        maintenance_window,
        maintenance_window_no_next_execution_time,
    ]

    service = build_ec2_service(
        env,
        build_scheduling_context(current_dt=quick_time(10, 0, 0), schedules=schedules),
    )
    result = list(service.describe_tagged_instances())
    assert len(result) == 1

    # only contains maintenance window with next_execution_time
    assert result[0].maintenance_windows == [
        maintenance_window.to_schedule(env.scheduler_frequency_minutes)
    ]


def instance_data_from(
    *,
    instance_id: str,
    instance_state: InstanceStateNameType,
    instance_type: InstanceTypeType,
    hibernate: bool = False,
) -> EC2Instance:
    if instance_state not in {"running", "stopped"}:
        raise ValueError(f"Unimplemented instance data conversion: {instance_state}")
    return EC2Instance(
        _id=instance_id,
        should_hibernate=hibernate,
        _current_state=instance_state,
        _instance_type=instance_type,
        _maintenance_windows=[],
        _tags={},
        _name="",
        _schedule_name="sched_name",
    )


def test_resize_instance(moto_backend: None) -> None:
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

    service: Final = build_ec2_service()
    service.resize_instance(instance, new_instance_type)

    assert (
        ec2.describe_instances(InstanceIds=[instance_id])["Reservations"][0][
            "Instances"
        ][0]["InstanceType"]
        == new_instance_type
    )


def test_start_instances(moto_backend: None) -> None:
    ec2: Final[EC2Client] = boto3.client("ec2")
    instance_type: Final[InstanceTypeType] = "m6g.xlarge"
    instances = create_instances_of_status(
        ec2, instance_type=instance_type, qty_stopped=7
    )

    service: Final = build_ec2_service()
    assert list(service.start_instances([])) == []

    instances_to_start: list[EC2Instance] = []
    for instance_id in instances.stopped_ids:
        instances_to_start.append(
            instance_data_from(
                instance_id=instance_id,
                instance_state="stopped",
                instance_type=instance_type,
            )
        )

    result = list(service.start_instances(instances_to_start))
    assert not result  # no errors

    ec2.get_waiter("instance_running").wait(InstanceIds=instances.stopped_ids)

    statuses = ec2.describe_instance_status(InstanceIds=instances.stopped_ids)
    for status in statuses["InstanceStatuses"]:
        assert status["InstanceState"]["Name"] == "running"


def test_start_instances_with_errors(moto_backend: None) -> None:
    ec2: Final[EC2Client] = boto3.client("ec2")
    instance_type: Final[InstanceTypeType] = "m6g.xlarge"
    instances = create_instances_of_status(
        ec2, instance_type=instance_type, qty_stopped=8
    )

    service: Final = build_ec2_service()

    good_instances: list[EC2Instance] = []
    bad_instances: list[EC2Instance] = []
    for instance_id in instances.stopped_ids:
        good_instances.append(
            instance_data_from(
                instance_id=instance_id,
                instance_state="stopped",
                instance_type=instance_type,
            )
        )
        # add a duplicate Instance with a bad identifier, interleaved
        bad_instance_id = "id-bad" + instance_id[6:]
        bad_instances.append(
            instance_data_from(
                instance_id=bad_instance_id,
                instance_state="stopped",
                instance_type=instance_type,
            )
        )

    # mix good/bad instance ids together to exercise bisect retry logic
    instances_to_start = good_instances + bad_instances
    random.shuffle(instances_to_start)
    result = list(service.start_instances(instances_to_start))

    for bad_instance in bad_instances:
        assert result.__contains__((bad_instance, ANY))

    ec2.get_waiter("instance_running").wait(InstanceIds=instances.stopped_ids)

    for status in ec2.describe_instance_status(
        InstanceIds=[instance.id for instance in good_instances]
    )["InstanceStatuses"]:
        assert status["InstanceState"]["Name"] == "running"


def test_stop_instances(moto_backend: None) -> None:
    ec2: Final[EC2Client] = boto3.client("ec2")
    instance_type: Final[InstanceTypeType] = "m6g.large"
    instances = create_instances_of_status(
        ec2, instance_type=instance_type, qty_running=52
    )

    service: Final = build_ec2_service()
    assert list(service.stop_instances([])) == []

    instances_to_stop: list[EC2Instance] = []
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


def test_stop_instances_with_errors(moto_backend: None) -> None:
    ec2: Final[EC2Client] = boto3.client("ec2")
    instance_type: Final[InstanceTypeType] = "m6g.large"
    instances = create_instances_of_status(
        ec2, instance_type=instance_type, qty_running=52
    )

    service: Final = build_ec2_service()

    instances_to_stop: list[EC2Instance] = []
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


def test_stop_instances_will_fallback_on_regular_stop_when_hibernate_errors() -> None:
    ec2: Final[EC2Client] = boto3.client("ec2")
    stub_ec2: Final = Stubber(ec2)
    scheduling_role = AssumedRole(
        account="123456789012",
        region="us-east-1",
        role_name="role-name",
        session=Session(),
    )

    setattr(scheduling_role.session, "client", MagicMock(return_value=ec2))

    service: Final = Ec2Service(
        assumed_scheduling_role=scheduling_role,
        scheduling_context=build_scheduling_context(quick_time(0, 0, 0)),
        logger=MockLogger(),
        env=MockSchedulingRequestEnvironment(),
    )

    my_instance_id: Final = "i-1234567890abcdef0"
    stub_ec2.add_client_error(
        "stop_instances",
        "UnsupportedHibernationConfiguration",
        expected_params={"InstanceIds": [my_instance_id], "Hibernate": True},
    )

    stub_ec2.add_response(
        "stop_instances",
        {
            "StoppingInstances": [
                {
                    "CurrentState": {"Code": EC2StateCode.STOPPING, "Name": "stopping"},
                    "InstanceId": my_instance_id,
                    "PreviousState": {"Code": EC2StateCode.RUNNING, "Name": "running"},
                }
            ]
        },
        {"InstanceIds": [my_instance_id]},
    )

    with stub_ec2:
        result = list(
            service.stop_instances(
                [
                    instance_data_from(
                        instance_id=my_instance_id,
                        instance_state="stopped",
                        instance_type="m6g.medium",
                        hibernate=True,
                    )
                ]
            )
        )
    stub_ec2.assert_no_pending_responses()

    instance_results: Final = {instance_id: status for (instance_id, status) in result}
    assert instance_results[my_instance_id] == "stopped"
