# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from unittest.mock import Mock, patch

import boto3

from instance_scheduler.schedulers.instance_states import InstanceStates
from tests.integration.helpers.ec2_helpers import get_current_state, stop_ec2_instances
from tests.integration.helpers.run_handler import simple_schedule
from tests.integration.helpers.schedule_helpers import quick_time


def willRaise(ex: Exception) -> None:
    raise ex


# https://docs.getmoto.org/en/latest/docs/services/patching_other_services.html


def test_ec2_starts_at_beginning_of_period(
    ec2_instance: str,
    ec2_instance_states: InstanceStates,
) -> None:
    # instance is already stopped
    stop_ec2_instances(ec2_instance)
    with simple_schedule(begintime="10:00", endtime="20:00") as context:
        # before start of period (populates state table)
        context.run_scheduling_request_handler(dt=quick_time(9, 55))
        assert get_current_state(ec2_instance) == "stopped"

        client_mock = Mock(wraps=boto3.client("ec2"))
        with patch(
            "instance_scheduler.util.session_manager.AssumedRole.client",
            lambda x, y: client_mock,
        ):
            client_mock.start_instances = lambda x, y: willRaise(
                Exception("start failure")
            )

            # start fails at beginning of period
            context.run_scheduling_request_handler(dt=quick_time(10, 0))
            assert get_current_state(ec2_instance) == "stopped"

        # retry
        context.run_scheduling_request_handler(dt=quick_time(10, 5))
        assert get_current_state(ec2_instance) == "running"
