# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

from freezegun.api import freeze_time

from instance_scheduler.configuration.scheduling_context import TagTemplate
from instance_scheduler.schedulers.instance_states import InstanceStates
from tests.integration.helpers.ec2_helpers import (
    get_current_state,
    get_tags,
    stop_ec2_instances,
)
from tests.integration.helpers.run_handler import simple_schedule
from tests.integration.helpers.schedule_helpers import quick_time
from tests.test_utils.mock_scheduling_request_environment import (
    MockSchedulingRequestEnvironment,
)


@freeze_time("2023-06-12 5:00:00")
def test_ec2_start_tag_is_applied_on_start(
    ec2_instance: str,
    ec2_instance_states: InstanceStates,
) -> None:
    """
    test that the start tag is applied with the correct substitutions
    note - the correct time substitution is actual time (from freeze_time) NOT schedule time (current_dt)
    """

    # instance is already stopped
    stop_ec2_instances(ec2_instance)
    mock_environ = MockSchedulingRequestEnvironment(
        start_tags=[
            "action=started by {scheduler} on {year}/{month}/{day} at {hour}:{minute} {timezone}"
        ]
    )
    with simple_schedule(begintime="10:00", endtime="20:00") as context:
        # before start of period (populates state table)
        context.run_scheduling_request_handler(dt=quick_time(9, 55))
        assert get_current_state(ec2_instance) == "stopped"
        # start of period
        context.run_scheduling_request_handler(
            dt=quick_time(10, 0), environment=mock_environ
        )

        assert get_current_state(ec2_instance) == "running"
        tags = get_tags(ec2_instance)

        assert tags.__contains__(
            {
                "Key": "action",
                "Value": f"started by {mock_environ.stack_name} on 2023/06/12 at 05:00 UTC",
            }
        )


@freeze_time("2023-06-12 15:00:00")
def test_ec2_stop_tag_is_applied_on_stop(
    ec2_instance: str,
    ec2_instance_states: InstanceStates,
) -> None:
    """
    test that the stop tag is applied with the correct substitutions
    note - the correct time substitution is actual time (from freeze_time) NOT schedule time (current_dt)
    """

    # instance is already stopped
    stop_ec2_instances(ec2_instance)
    mock_environ = MockSchedulingRequestEnvironment(
        stop_tags=[
            "action=stopped by {scheduler} on {year}/{month}/{day} at {hour}:{minute} {timezone}"
        ]
    )

    with simple_schedule(begintime="10:00", endtime="20:00") as context:
        # before end of period (populates state table)
        context.run_scheduling_request_handler(dt=quick_time(19, 55))
        assert get_current_state(ec2_instance) == "running"
        # end of period

        context.run_scheduling_request_handler(
            dt=quick_time(20, 0), environment=mock_environ
        )

        assert get_current_state(ec2_instance) == "stopped"
        tags = get_tags(ec2_instance)

        assert tags.__contains__(
            {
                "Key": "action",
                "Value": f"stopped by {mock_environ.stack_name} on 2023/06/12 at 15:00 UTC",
            }
        )


def test_ec2_start_stop_tags_are_mutually_exclusive(
    ec2_instance: str,
    ec2_instance_states: InstanceStates,
) -> None:
    """when start tags are applied, stop tags should be removed and vice-versa"""
    started_tag1: TagTemplate = {"Key": "started1", "Value": "start1"}
    started_tag2: TagTemplate = {"Key": "started2", "Value": "start2"}
    stopped_tag1: TagTemplate = {"Key": "stopped1", "Value": "stop1"}
    stopped_tag2: TagTemplate = {"Key": "stopped2", "Value": "stop2"}

    mock_environ = MockSchedulingRequestEnvironment(
        start_tags=[
            f"{started_tag1['Key']}={started_tag1['Value']}",
            f"{started_tag2['Key']}={started_tag2['Value']}",
        ],
        stop_tags=[
            f"{stopped_tag1['Key']}={stopped_tag1['Value']}",
            f"{stopped_tag2['Key']}={stopped_tag2['Value']}",
        ],
    )

    with simple_schedule(begintime="10:00", endtime="20:00") as context:
        stop_ec2_instances(ec2_instance)
        # before period start (populates state table)
        context.run_scheduling_request_handler(dt=quick_time(9, 55))

        # first start
        context.run_scheduling_request_handler(
            dt=quick_time(10, 0), environment=mock_environ
        )

        instance_tags = get_tags(ec2_instance)
        assert started_tag1 in instance_tags
        assert started_tag2 in instance_tags
        assert stopped_tag1 not in instance_tags
        assert stopped_tag2 not in instance_tags

        # stop
        context.run_scheduling_request_handler(
            dt=quick_time(20, 0), environment=mock_environ
        )
        instance_tags = get_tags(ec2_instance)
        assert started_tag1 not in instance_tags
        assert started_tag2 not in instance_tags
        assert stopped_tag1 in instance_tags
        assert stopped_tag2 in instance_tags

        # second start
        context.run_scheduling_request_handler(
            dt=quick_time(10, 0), environment=mock_environ
        )
        instance_tags = get_tags(ec2_instance)
        assert started_tag1 in instance_tags
        assert started_tag2 in instance_tags
        assert stopped_tag1 not in instance_tags
        assert stopped_tag2 not in instance_tags
