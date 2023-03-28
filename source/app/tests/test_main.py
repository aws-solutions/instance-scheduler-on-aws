# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from unittest.mock import patch

from instance_scheduler.main import lambda_handler


class MockContext:
    def __init__(self):
        self.log_group_name = "My log group"


@patch("instance_scheduler.main.SchedulerRequestHandler")
def test_scheduler_request_handler_called(mock_handler):
    """SchedulerRequestHandler handle_request is called when is_handling_request is True"""
    mock_handler.is_handling_request.return_value = True
    my_response = "Everything's great!"
    mock_handler.return_value.handle_request.return_value = my_response
    mock_handler.__name__ = "My handler name"

    assert lambda_handler({}, MockContext()) == my_response

    mock_handler.return_value.handle_request.assert_called_once()
