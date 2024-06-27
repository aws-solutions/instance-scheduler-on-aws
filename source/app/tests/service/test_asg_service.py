# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from unittest.mock import MagicMock, patch

from boto3 import Session

from instance_scheduler.service.asg import AsgService
from instance_scheduler.util.session_manager import AssumedRole
from tests.test_utils.mock_asg_environment import MockAsgEnvironment


def test_get_schedulable_groups_respects_5_tags_at_a_time_limit(
    moto_backend: None,
) -> None:
    env = MockAsgEnvironment()
    asg_service = AsgService(
        assumed_asg_scheduling_role=AssumedRole(
            account="123456789012",
            region="us-east-1",
            role_name="role-name",
            session=Session(),
        ),
        schedule_tag_key=env.schedule_tag_key,
        asg_scheduled_tag_key=env.scheduled_tag_key,
        rule_prefix=env.rule_prefix,
    )

    with patch.object(asg_service, "_autoscaling") as mock_autoscaling_client:
        paginator = MagicMock()
        mock_autoscaling_client.get_paginator.return_value = paginator
        schedule_names = [
            "a",
            "b",
            "c",
            "d",
            "e",
            "f",
            "g",
            "h",
        ]

        list(asg_service.get_schedulable_groups(schedule_names))

        paginator.paginate.assert_called()
        requested_schedule_names = []

        # assert that no reqeust exceeded 5 names at once
        for paginate_call in paginator.paginate.call_args_list:
            assert len(paginate_call.kwargs["Filters"][0]["Values"]) <= 5
            requested_schedule_names.extend(
                paginate_call.kwargs["Filters"][0]["Values"]
            )

        # assert that all schedules were actually requested
        assert len(requested_schedule_names) == 8
        assert all(
            schedule_name in requested_schedule_names
            for schedule_name in schedule_names
        )
