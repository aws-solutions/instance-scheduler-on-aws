# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import dataclasses
from datetime import datetime, timezone

import boto3
from freezegun.api import freeze_time
from mypy_boto3_ec2.client import EC2Client

from instance_scheduler.configuration.scheduling_context import TagTemplate
from instance_scheduler.handler.scheduling_request import SchedulingRequestHandler
from instance_scheduler.schedulers.instance_states import InstanceStates
from instance_scheduler.util.app_env import AppEnv
from tests.context import MockLambdaContext
from tests.integration.helpers.ec2_helpers import get_tags
from tests.integration.helpers.schedule_helpers import quick_time
from tests.integration.helpers.scheduling_context_builder import (
    build_context,
    build_scheduling_event,
)


@freeze_time("2023-06-12 5:00:00")
def test_ec2_start_tag_is_applied_on_start(
    app_env: AppEnv, ec2_instance: str, ec2_instance_states: InstanceStates
) -> None:
    """
    test that the start tag is applied with the correct substitutions
    note - the correct time substitution is actual time (from freeze_time) NOT schedule time (current_dt)
    """
    context = build_context(
        current_dt=datetime(2023, 6, 12, 10, 0, 0, tzinfo=timezone.utc),
        started_tags=[
            {
                "Key": "action",
                "Value": "started by {scheduler} on {year}/{month}/{day} at {hour}:{minute} {timezone}",
            }
        ],
    )
    event = build_scheduling_event(context)

    # ----------------------------EC2 Instance-------------------------#
    ec2_client: EC2Client = boto3.client("ec2")
    ec2_client.stop_instances(InstanceIds=[ec2_instance])

    # ------------------------Last Desired State------------------------#
    ec2_instance_states.set_instance_state(ec2_instance, "stopped")
    ec2_instance_states.save()

    # -------------------run handler------------------------#
    handler = SchedulingRequestHandler(event, MockLambdaContext())
    handler.handle_request()

    # ---------------------validate result---------------------#

    tags = get_tags(ec2_instance)

    assert tags.__contains__(
        {
            "Key": "action",
            "Value": f"started by {app_env.stack_name} on 2023/06/12 at 05:00 UTC",
        }
    )


@freeze_time("2023-06-12 15:00:00")
def test_ec2_stop_tag_is_applied_on_stop(
    app_env: AppEnv, ec2_instance: str, ec2_instance_states: InstanceStates
) -> None:
    """
    test that the stop tag is applied with the correct substitutions
    note - the correct time substitution is actual time (from freeze_time) NOT schedule time (current_dt)
    """
    context = build_context(
        current_dt=datetime(2023, 6, 12, 20, 0, 0, tzinfo=timezone.utc),
        stopped_tags=[
            {
                "Key": "action",
                "Value": "stopped by {scheduler} on {year}/{month}/{day} at {hour}:{minute} {timezone}",
            }
        ],
    )
    event = build_scheduling_event(context)

    # ----------------------------EC2 Instance-------------------------#
    ec2_client: EC2Client = boto3.client("ec2")
    ec2_client.start_instances(InstanceIds=[ec2_instance])

    # ------------------------Last Desired State------------------------#
    ec2_instance_states.set_instance_state(ec2_instance, "running")
    ec2_instance_states.save()

    # -------------------run handler------------------------#
    handler = SchedulingRequestHandler(event, MockLambdaContext())
    handler.handle_request()

    # ---------------------validate result---------------------#

    tags = get_tags(ec2_instance)

    assert tags.__contains__(
        {
            "Key": "action",
            "Value": f"stopped by {app_env.stack_name} on 2023/06/12 at 15:00 UTC",
        }
    )


def test_ec2_start_stop_tags_are_mutually_exclusive(
    ec2_instance: str, ec2_instance_states: InstanceStates
) -> None:
    """when start tags are applied, stop tags should be removed and vice-versa"""
    started_tag1: TagTemplate = {"Key": "started1", "Value": "start1"}
    started_tag2: TagTemplate = {"Key": "started2", "Value": "start2"}
    stopped_tag1: TagTemplate = {"Key": "stopped1", "Value": "stop1"}
    stopped_tag2: TagTemplate = {"Key": "stopped2", "Value": "stop2"}

    context = build_context(
        current_dt=quick_time(10, 0, 0),
        started_tags=[started_tag1, started_tag2],
        stopped_tags=[stopped_tag1, stopped_tag2],
    )
    event = build_scheduling_event(context)

    # ----------------------------initial setup-------------------------#
    ec2_client: EC2Client = boto3.client("ec2")
    ec2_client.stop_instances(InstanceIds=[ec2_instance])
    ec2_instance_states.set_instance_state(ec2_instance, "stopped")
    ec2_instance_states.save()

    # ------------------------first start------------------------#
    handler = SchedulingRequestHandler(event, MockLambdaContext())
    handler.handle_request()

    instance_tags = get_tags(ec2_instance)
    assert started_tag1 in instance_tags
    assert started_tag2 in instance_tags
    assert stopped_tag1 not in instance_tags
    assert stopped_tag2 not in instance_tags

    # -------------------stop------------------------#
    context = dataclasses.replace(context, current_dt=quick_time(20, 0, 0))
    event = build_scheduling_event(context)
    handler = SchedulingRequestHandler(event, MockLambdaContext())
    handler.handle_request()

    instance_tags = get_tags(ec2_instance)
    assert started_tag1 not in instance_tags
    assert started_tag2 not in instance_tags
    assert stopped_tag1 in instance_tags
    assert stopped_tag2 in instance_tags

    # ---------------------start again---------------------#
    context = dataclasses.replace(context, current_dt=quick_time(10, 0, 0))
    event = build_scheduling_event(context)
    handler = SchedulingRequestHandler(event, MockLambdaContext())
    handler.handle_request()

    instance_tags = get_tags(ec2_instance)
    assert started_tag1 in instance_tags
    assert started_tag2 in instance_tags
    assert stopped_tag1 not in instance_tags
    assert stopped_tag2 not in instance_tags
