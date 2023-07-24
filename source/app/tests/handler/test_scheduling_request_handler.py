# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from unittest.mock import ANY, MagicMock, patch

from instance_scheduler.handler.scheduling_request import SchedulingRequestHandler
from tests.context import MockLambdaContext
from tests.integration.helpers.schedule_helpers import quick_time
from tests.integration.helpers.scheduling_context_builder import (
    build_context,
    build_scheduling_event,
)


@patch("instance_scheduler.handler.scheduling_request.Session")
def test_scheduler_uses_regional_sts_endpoint(mock_session: MagicMock) -> None:
    mock_client = MagicMock()
    mock_session.return_value.client = mock_client
    region_name = "executing-region"
    mock_session.return_value.region_name = region_name

    context = build_context(current_dt=quick_time(10, 0, 0), service="rds")
    event = build_scheduling_event(context)
    handler = SchedulingRequestHandler(event, MockLambdaContext())
    handler.sts

    mock_client.assert_called_with(
        "sts",
        region_name=region_name,
        endpoint_url=f"https://sts.{region_name}.amazonaws.com",
        config=ANY,
    )
