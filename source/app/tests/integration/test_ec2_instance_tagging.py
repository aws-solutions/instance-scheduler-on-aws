# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import pytest
from freezegun.api import freeze_time
from instance_scheduler.configuration.scheduling_context import SchedulingContext
from instance_scheduler.observability.tag_keys import InformationalTagKey
from tests.integration.helpers.ec2_helpers import (
    get_current_state,
    get_tags,
    stop_ec2_instances,
)
from tests.integration.helpers.run_handler import simple_schedule
from tests.integration.helpers.schedule_helpers import quick_time


@freeze_time("2023-06-12 5:00:00")
@pytest.mark.skip("moto does not support RGTApi write_tags for EC2 yet")
def test_ec2_informational_tags_applied_on_start(
    ec2_instance: str,
    scheduling_context: SchedulingContext,
) -> None:
    """
    test that informational tags are applied when starting an instance
    """

    # instance is already stopped
    stop_ec2_instances(ec2_instance)

    with simple_schedule(begintime="10:00", endtime="20:00") as context:
        # before start of period (populates state table)
        context.run_scheduling_request_handler(dt=quick_time(9, 55))
        assert get_current_state(ec2_instance) == "stopped"
        # start of period
        context.run_scheduling_request_handler(dt=quick_time(10, 0))

        assert get_current_state(ec2_instance) == "running"
        tags = get_tags(ec2_instance)

        # Check for informational tags
        assert any(tag["Key"] == InformationalTagKey.MANAGED_BY.value for tag in tags)
        assert any(
            tag["Key"] == InformationalTagKey.LAST_ACTION.value
            and "Started (2023-06-12 05:00:00 UTC)" in tag["Value"]
            for tag in tags
        )


@freeze_time("2023-06-12 15:00:00")
@pytest.mark.skip("moto does not support RGTApi write_tags for EC2 yet")
def test_ec2_informational_tags_applied_on_stop(
    ec2_instance: str,
    scheduling_context: SchedulingContext,
) -> None:
    """
    test that informational tags are applied when stopping an instance
    """

    # instance is already stopped
    stop_ec2_instances(ec2_instance)

    with simple_schedule(begintime="10:00", endtime="20:00") as context:
        # before end of period (populates state table)
        context.run_scheduling_request_handler(dt=quick_time(19, 55))
        assert get_current_state(ec2_instance) == "running"
        # end of period

        context.run_scheduling_request_handler(dt=quick_time(20, 0))

        assert get_current_state(ec2_instance) == "stopped"
        tags = get_tags(ec2_instance)

        # Check for informational tags
        assert any(tag["Key"] == InformationalTagKey.MANAGED_BY.value for tag in tags)
        assert any(
            tag["Key"] == InformationalTagKey.LAST_ACTION.value
            and "Stopped (2023-06-12 15:00:00 UTC)" in tag["Value"]
            for tag in tags
        )


@pytest.mark.skip("moto does not support RGTApi write_tags for EC2 yet")
def test_ec2_informational_tags_update_on_actions(
    ec2_instance: str,
    scheduling_context: SchedulingContext,
) -> None:
    """test that informational tags are updated correctly on start/stop actions"""
    with simple_schedule(begintime="10:00", endtime="20:00") as context:
        stop_ec2_instances(ec2_instance)
        # before period start (populates state table)
        context.run_scheduling_request_handler(dt=quick_time(9, 55))

        # start instance
        context.run_scheduling_request_handler(dt=quick_time(10, 0))

        instance_tags = get_tags(ec2_instance)
        # Check managed by tag is present
        assert any(
            tag["Key"] == InformationalTagKey.MANAGED_BY.value for tag in instance_tags
        )
        # Check last action shows start
        assert any(
            tag["Key"] == InformationalTagKey.LAST_ACTION.value
            and "Started" in tag["Value"]
            for tag in instance_tags
        )
        # No error tags should be present
        assert not any(
            tag["Key"] == InformationalTagKey.ERROR.value for tag in instance_tags
        )

        # stop instance
        context.run_scheduling_request_handler(dt=quick_time(20, 0))
        instance_tags = get_tags(ec2_instance)
        # Check managed by tag is still present
        assert any(
            tag["Key"] == InformationalTagKey.MANAGED_BY.value for tag in instance_tags
        )
        # Check last action now shows stop
        assert any(
            tag["Key"] == InformationalTagKey.LAST_ACTION.value
            and "Stopped" in tag["Value"]
            for tag in instance_tags
        )
        # No error tags should be present
        assert not any(
            tag["Key"] == InformationalTagKey.ERROR.value for tag in instance_tags
        )
