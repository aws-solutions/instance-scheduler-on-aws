# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from contextlib import contextmanager
from typing import Iterator
from unittest.mock import MagicMock, patch

from _pytest.fixtures import fixture
from urllib3 import HTTPResponse


@contextmanager
def override_should_send_metric(return_value: bool) -> Iterator[None]:
    with patch(
        "instance_scheduler.ops_metrics.metrics.should_collect_metric"
    ) as should_collect_metrics_func:
        should_collect_metrics_func.return_value = return_value
        yield


@fixture
def mock_metrics_endpoint() -> Iterator[MagicMock]:
    with patch(
        "instance_scheduler.ops_metrics.metrics.http.request"
    ) as post_request_func:
        post_response = HTTPResponse(status=200)
        post_request_func.return_value = post_response

        yield post_request_func
