# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

from botocore.exceptions import ClientError
from instance_scheduler.configuration.scheduling_context import SchedulingContext
from tests.integration.helpers.boto_client_helpers import mock_specific_client
from tests.integration.helpers.ec2_helpers import get_current_state, stop_ec2_instances
from tests.integration.helpers.run_handler import simple_schedule
from tests.integration.helpers.schedule_helpers import quick_time


def will_raise(ex: Exception) -> None:
    raise ex


# https://docs.getmoto.org/en/latest/docs/services/patching_other_services.html


def test_ec2_retries_start_after_a_start_failure(
    ec2_instance: str,
    scheduling_context: SchedulingContext,
) -> None:
    # instance is already stopped
    stop_ec2_instances(ec2_instance)
    with simple_schedule(begintime="10:00", endtime="20:00") as context:
        # before start of period (populates state table)
        context.run_scheduling_request_handler(dt=quick_time(9, 55))
        assert get_current_state(ec2_instance) == "stopped"

        with mock_specific_client("ec2") as mock_ec2_client:
            mock_ec2_client.start_instances = lambda **kwargs: will_raise(
                ClientError(
                    {"Error": {"Code": "TestError", "Message": "start failure"}},
                    "StartInstances",
                )
            )

            # start fails at beginning of period
            context.run_scheduling_request_handler(dt=quick_time(10, 0))
            assert get_current_state(ec2_instance) == "stopped"

        # retry
        context.run_scheduling_request_handler(dt=quick_time(10, 5))
        assert get_current_state(ec2_instance) == "running"
