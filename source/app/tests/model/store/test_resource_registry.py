# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import pytest
from instance_scheduler.model.managed_instance import (
    AsgConfiguration,
    RegisteredAsgInstance,
    RegisteredEc2Instance,
    RegisteredRdsInstance,
    RegistryKey,
)
from instance_scheduler.model.store.dynamo_resource_registry import (
    DynamoResourceRegistry,
)
from instance_scheduler.model.store.in_memory_resource_registry import (
    InMemoryResourceRegistry,
)
from instance_scheduler.model.store.resource_registry import (
    ResourceAlreadyRegisteredException,
    ResourceRegistry,
    UnknownResourceException,
)
from instance_scheduler.scheduling.states import InstanceState
from instance_scheduler.util.arn import ARN
from tests.test_utils.unordered_list import UnorderedList


@pytest.fixture(params=["dynamo", "in_memory"])
def resource_registry(
    request: pytest.FixtureRequest, registry_table: str
) -> ResourceRegistry:
    if request.param == "dynamo":
        return DynamoResourceRegistry(registry_table)
    else:
        return InMemoryResourceRegistry()


def test_find_all(resource_registry: ResourceRegistry) -> None:
    instances = [
        RegisteredEc2Instance(
            account="123456789012",
            region="eu-west-1",
            resource_id="XXXXXXXXXXXX",
            arn=ARN("arn:aws:ec2:eu-west-1:123456789012:instance/XXXXXXXXXXXX"),
            schedule="schedule-name",
            name="my-ec2-instance",
            stored_state=InstanceState.RUNNING,
        ),
        RegisteredEc2Instance(
            account="123456789012",
            region="eu-west-1",
            resource_id="YYYYYYYYYYYY",
            arn=ARN("arn:aws:ec2:eu-west-1:123456789012:instance/YYYYYYYYYYYY"),
            schedule="schedule-name",
            name="my-ec2-instance",
            stored_state=InstanceState.RUNNING,
        ),
        RegisteredRdsInstance(
            account="123456789012",
            region="eu-west-2",
            resource_id="XXXXXXXXXXXX",
            arn=ARN("arn:aws:rds:eu-west-2:123456789012:cluster:XXXXXXXXXXXX"),
            schedule="schedule-name",
            name="my-ec2-instance",
            stored_state=InstanceState.RUNNING,
        ),
        RegisteredEc2Instance(
            account="123456789012",
            region="eu-west-2",
            resource_id="YYYYYYYYYYYY",
            arn=ARN("arn:aws:ec2:eu-west-2:123456789012:instance/YYYYYYYYYYYY"),
            schedule="schedule-name",
            name="my-ec2-instance",
            stored_state=InstanceState.RUNNING,
        ),
        RegisteredAsgInstance(
            account="111122223333",
            region="eu-west-1",
            resource_id="XXXXXXXXXXXX",
            arn=ARN(
                "arn:aws:autoscaling:eu-west-1:111122223333:autoScalingGroup:XXXXXXXXXXXX"
            ),
            schedule="schedule-name",
            name="my-asg-instance",
            stored_state=InstanceState.CONFIGURED,
            last_configured=AsgConfiguration(
                last_updated="2025-08-07",
                min=1,
                desired=2,
                max=4,
                schedule_hash="ABCDEFG",
                valid_until="2025-08-09",
            ),
        ),
    ]

    for instance in instances:
        resource_registry.put(instance)

    assert list(resource_registry.find_all()) == UnorderedList(instances)


def test_find_by_account(resource_registry: ResourceRegistry) -> None:
    ec2_instance = RegisteredEc2Instance(
        account="123456789012",
        region="eu-west-1",
        resource_id="XXXXXXXXXXXX",
        arn=ARN("arn:aws:ec2:eu-west-1:123456789012:instance/XXXXXXXXXXXX"),
        schedule="schedule-name",
        name="my-ec2-instance",
        stored_state=InstanceState.RUNNING,
    )

    rds_instance = RegisteredRdsInstance(
        account="123456789012",
        region="eu-west-1",
        resource_id="XXXXXXXXXXXX",
        arn=ARN("arn:aws:rds:eu-west-1:123456789012:db:XXXXXXXXXXXX"),
        schedule="schedule-name",
        name="my-rds-instance",
        stored_state=InstanceState.RUNNING,
    )

    asg_instance = RegisteredAsgInstance(
        account="111122223333",
        region="eu-west-1",
        resource_id="XXXXXXXXXXXX",
        arn=ARN(
            "arn:aws:autoscaling:eu-west-1:111122223333:autoScalingGroup:XXXXXXXXXXXX"
        ),
        schedule="schedule-name",
        name="my-asg-instance",
        stored_state=InstanceState.CONFIGURED,
        last_configured=AsgConfiguration(
            last_updated="2025-08-07",
            min=1,
            desired=2,
            max=4,
            schedule_hash="ABCDEFG",
            valid_until="2025-08-09",
        ),
    )

    resource_registry.put(ec2_instance)
    resource_registry.put(rds_instance)
    resource_registry.put(asg_instance)

    assert list(resource_registry.find_by_account("123456789012")) == UnorderedList(
        [
            ec2_instance,
            rds_instance,
        ]
    )
    assert list(resource_registry.find_by_account("111122223333")) == [asg_instance]


def test_find_by_target(resource_registry: ResourceRegistry) -> None:
    t1 = [
        RegisteredEc2Instance(
            account="123456789012",
            region="eu-west-1",
            resource_id="XXXXXXXXXXXX",
            arn=ARN("arn:aws:ec2:eu-west-1:123456789012:instance/XXXXXXXXXXXX"),
            schedule="schedule-name",
            name="my-ec2-instance",
            stored_state=InstanceState.RUNNING,
        ),
        RegisteredEc2Instance(
            account="123456789012",
            region="eu-west-1",
            resource_id="YYYYYYYYYYYY",
            arn=ARN("arn:aws:ec2:eu-west-1:123456789012:instance/YYYYYYYYYYYY"),
            schedule="schedule-name",
            name="my-ec2-instance",
            stored_state=InstanceState.RUNNING,
        ),
    ]

    t2 = [
        RegisteredEc2Instance(
            account="123456789012",
            region="eu-west-2",
            resource_id="XXXXXXXXXXXX",
            arn=ARN("arn:aws:ec2:eu-west-2:123456789012:instance/XXXXXXXXXXXX"),
            schedule="schedule-name",
            name="my-ec2-instance",
            stored_state=InstanceState.RUNNING,
        ),
        RegisteredEc2Instance(
            account="123456789012",
            region="eu-west-2",
            resource_id="YYYYYYYYYYYY",
            arn=ARN("arn:aws:ec2:eu-west-2:123456789012:instance/YYYYYYYYYYYY"),
            schedule="schedule-name",
            name="my-ec2-instance",
            stored_state=InstanceState.RUNNING,
        ),
    ]

    for instance in t1 + t2:
        resource_registry.put(instance)

    assert list(
        resource_registry.find_by_scheduling_target("123456789012", "eu-west-1", "ec2")
    ) == UnorderedList(t1)
    assert list(
        resource_registry.find_by_scheduling_target("123456789012", "eu-west-2", "ec2")
    ) == UnorderedList(t2)


def test_put_without_overwrite_raises_exception(
    resource_registry: ResourceRegistry,
) -> None:
    instance = RegisteredEc2Instance(
        account="123456789012",
        region="eu-west-1",
        resource_id="XXXXXXXXXXXX",
        arn=ARN("arn:aws:ec2:eu-west-1:123456789012:instance/XXXXXXXXXXXX"),
        schedule="schedule-name",
        name="my-instance",
        stored_state=InstanceState.RUNNING,
    )
    resource_registry.put(instance)

    with pytest.raises(ResourceAlreadyRegisteredException):
        resource_registry.put(instance, overwrite=False)


def test_put_with_overwrite_succeeds(resource_registry: ResourceRegistry) -> None:
    original_instance = RegisteredEc2Instance(
        account="123456789012",
        region="eu-west-1",
        resource_id="XXXXXXXXXXXX",
        arn=ARN("arn:aws:ec2:eu-west-1:123456789012:instance/XXXXXXXXXXXX"),
        schedule="original-schedule",
        name="original-name",
        stored_state=InstanceState.STOPPED,
    )

    updated_instance = RegisteredEc2Instance(
        account="123456789012",
        region="eu-west-1",
        resource_id="XXXXXXXXXXXX",
        arn=ARN("arn:aws:ec2:eu-west-1:123456789012:instance/XXXXXXXXXXXX"),
        schedule="updated-schedule",
        name="updated-name",
        stored_state=InstanceState.RUNNING,
    )

    resource_registry.put(original_instance)
    resource_registry.put(updated_instance, overwrite=True)

    result = list(resource_registry.find_by_account("123456789012"))
    assert result == [updated_instance]


def test_delete_with_error_if_missing_raises_exception(
    resource_registry: ResourceRegistry,
) -> None:
    key = RegistryKey(
        account="123456789012",
        region="eu-west-1",
        service="ec2",
        resource_type="instance",
        resource_id="NONEXISTENT",
    )

    with pytest.raises(UnknownResourceException):
        resource_registry.delete(key, error_if_missing=True)


def test_delete_without_error_if_missing_succeeds(
    resource_registry: ResourceRegistry,
) -> None:
    key = RegistryKey(
        account="123456789012",
        region="eu-west-1",
        service="ec2",
        resource_type="instance",
        resource_id="NONEXISTENT",
    )

    # Should not raise an exception
    resource_registry.delete(key, error_if_missing=False)


def test_delete_existing_resource(resource_registry: ResourceRegistry) -> None:
    instance = RegisteredEc2Instance(
        account="123456789012",
        region="eu-west-1",
        resource_id="XXXXXXXXXXXX",
        arn=ARN("arn:aws:ec2:eu-west-1:123456789012:instance/XXXXXXXXXXXX"),
        schedule="schedule-name",
        name="my-instance",
        stored_state=InstanceState.RUNNING,
    )

    resource_registry.put(instance)
    assert list(resource_registry.find_by_account("123456789012")) == [instance]

    resource_registry.delete(instance.key)
    assert list(resource_registry.find_by_account("123456789012")) == []


def test_get_existing_resource(resource_registry: ResourceRegistry) -> None:
    instance = RegisteredEc2Instance(
        account="123456789012",
        region="eu-west-1",
        resource_id="XXXXXXXXXXXX",
        arn=ARN("arn:aws:ec2:eu-west-1:123456789012:instance/XXXXXXXXXXXX"),
        schedule="schedule-name",
        name="my-instance",
        stored_state=InstanceState.RUNNING,
    )

    resource_registry.put(instance)
    result = resource_registry.get(instance.key)
    assert result == instance


def test_get_nonexistent_resource(resource_registry: ResourceRegistry) -> None:
    key = RegistryKey(
        account="123456789012",
        region="eu-west-1",
        service="ec2",
        resource_type="instance",
        resource_id="NONEXISTENT",
    )

    result = resource_registry.get(key)
    assert result is None


def test_get_after_delete(resource_registry: ResourceRegistry) -> None:
    instance = RegisteredEc2Instance(
        account="123456789012",
        region="eu-west-1",
        resource_id="XXXXXXXXXXXX",
        arn=ARN("arn:aws:ec2:eu-west-1:123456789012:instance/XXXXXXXXXXXX"),
        schedule="schedule-name",
        name="my-instance",
        stored_state=InstanceState.RUNNING,
    )

    resource_registry.put(instance)
    assert resource_registry.get(instance.key) == instance

    resource_registry.delete(instance.key)
    assert resource_registry.get(instance.key) is None
