# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import uuid
from typing import Iterator
from unittest.mock import MagicMock, patch

from _pytest.fixtures import fixture
from requests import Response

solution_metrics_uuid = uuid.UUID("3d522722-236f-4484-bbd7-e9b1da1bb347")


@fixture
def metrics_enabled() -> Iterator[None]:
    with patch(
        "instance_scheduler.ops_metrics.metrics.should_collect_metric"
    ) as should_collect_metrics_func:
        with patch(
            "instance_scheduler.ops_metrics.metrics._get_deployment_uuid"
        ) as get_deployment_uuid_func:
            should_collect_metrics_func.return_value = True
            get_deployment_uuid_func.return_value = solution_metrics_uuid
            yield


@fixture
def mock_metrics_endpoint(metrics_enabled: None) -> Iterator[MagicMock]:
    with patch("requests.post") as post_request_func:
        post_response = Response()
        post_response.status_code = 200
        post_request_func.return_value = post_response

        yield post_request_func
