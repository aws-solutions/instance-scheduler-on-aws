# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import os
from contextlib import contextmanager
from typing import Iterator
from unittest.mock import MagicMock, call, patch

import pytest
from _pytest.fixtures import fixture
from boto3.session import Session

from instance_scheduler.handler.environments.scheduling_request_environment import (
    SchedulingRequestEnvironment,
)
from instance_scheduler.service import RdsService
from instance_scheduler.service.rds import RdsTagDescription
from instance_scheduler.util.session_manager import AssumedRole
from tests.integration.helpers.rds_helpers import (
    create_rds_clusters,
    create_rds_instances,
)
from tests.integration.helpers.schedule_helpers import quick_time
from tests.integration.helpers.scheduling_context_builder import (
    build_scheduling_context,
)
from tests.logger import MockLogger
from tests.test_utils.mock_scheduling_request_environment import (
    MockSchedulingRequestEnvironment,
)


def build_rds_service(
    env: SchedulingRequestEnvironment = MockSchedulingRequestEnvironment(),
) -> RdsService:
    return RdsService(
        assumed_scheduling_role=AssumedRole(
            account="123456789012",
            region="us-east-1",
            role_name="role-name",
            session=Session(),
        ),
        scheduling_context=build_scheduling_context(quick_time(0, 0, 0)),
        logger=MockLogger(),
        env=env,
    )


def test_rds_service_attributes() -> None:
    service = build_rds_service()
    assert service.service_name == "rds"


@fixture
def mock_boto_client() -> Iterator[MagicMock]:
    with patch(
        "instance_scheduler.service.rds.get_client_with_standard_retry"
    ) as get_client_func:
        mock = MagicMock()
        get_client_func.return_value = mock

        # these are necessary to avoid an infinite loop
        mock.describe_db_instances.return_value = {"Marker": ""}
        mock.describe_db_clusters.return_value = {"Marker": ""}

        yield mock


@contextmanager
def mock_tagged_resources(
    rds_service: RdsService, tagged_resources: RdsTagDescription
) -> Iterator[None]:
    with patch.object(rds_service, "rds_resource_tags", tagged_resources):
        yield


def test_describes_clusters_when_only_neptune_enabled(
    mock_boto_client: MagicMock,
) -> None:
    env = MockSchedulingRequestEnvironment(
        enable_rds_service=False,
        enable_rds_clusters=False,
        enable_neptune_service=True,
        enable_docdb_service=False,
    )

    rds_service = build_rds_service(env)

    with mock_tagged_resources(
        rds_service,
        {
            "db": {"instanceArn": {"Schedule": "test-schedule"}},
            "cluster": {"clusterArn": {"Schedule": "test-schedule"}},
        },
    ):
        list(rds_service.describe_tagged_instances())

    mock_boto_client.get_paginator.assert_has_calls(
        [call("describe_db_clusters")],
    )


def test_describes_clusters_when_only_docdb_enabled(
    mock_boto_client: MagicMock,
) -> None:
    env = MockSchedulingRequestEnvironment(
        enable_rds_service=False,
        enable_rds_clusters=False,
        enable_neptune_service=False,
        enable_docdb_service=True,
    )

    rds_service = build_rds_service(env)

    with mock_tagged_resources(
        rds_service,
        {
            "db": {"instanceArn": {"Schedule": "test-schedule"}},
            "cluster": {"clusterArn": {"Schedule": "test-schedule"}},
        },
    ):
        list(rds_service.describe_tagged_instances())

    mock_boto_client.get_paginator.assert_has_calls(
        [call("describe_db_clusters")],
    )


def test_skips_describe_instances_when_no_tagged_instances_found(
    mock_boto_client: MagicMock,
) -> None:
    env = MockSchedulingRequestEnvironment(
        enable_rds_service=True,
        enable_rds_clusters=True,
        enable_neptune_service=True,
        enable_docdb_service=True,
    )

    rds_service = build_rds_service(env)

    with mock_tagged_resources(
        rds_service,
        {"db": {}, "cluster": {"clusterArn": {"Schedule": "test-schedule"}}},
    ):
        list(rds_service.describe_tagged_instances())

    # did call clusters
    mock_boto_client.get_paginator.assert_has_calls(
        [call("describe_db_clusters")],
    )

    # did not call instances
    with pytest.raises(AssertionError):
        mock_boto_client.get_paginator.assert_has_calls(
            [call("describe_db_instances")],
        )


def test_skips_describe_clusters_when_no_tagged_clusters_found(
    mock_boto_client: MagicMock,
) -> None:
    env = MockSchedulingRequestEnvironment(
        enable_rds_service=True,
        enable_rds_clusters=True,
        enable_neptune_service=True,
        enable_docdb_service=True,
    )
    rds_service = build_rds_service(env)

    with mock_tagged_resources(
        rds_service,
        {"db": {"someArn": {"Schedule": "test-schedule"}}, "cluster": {}},
    ):
        list(rds_service.describe_tagged_instances())

    # did call instances
    mock_boto_client.get_paginator.assert_has_calls(
        [call("describe_db_instances")],
    )

    # did not call clusters
    with pytest.raises(AssertionError):
        mock_boto_client.get_paginator.assert_has_calls(
            [call("describe_db_clusters")],
        )


def test_describe_instances_respects_50_arn_filter_limit(moto_backend: None) -> None:
    os.environ["MOTO_RDS_SNAPSHOT_LIMIT"] = "200"
    # see ADR-0007
    rds_instances = create_rds_instances(150)
    rds_service = build_rds_service()

    with patch.object(rds_service, "_rds_client") as mock_rds_client:
        paginator = MagicMock()
        mock_rds_client.get_paginator.return_value = paginator

        list(rds_service.get_in_scope_rds_instances())

        paginator.paginate.assert_called()
        requested_rds_arns = []

        # assert that no reqeust exceeded 50 names in the filter
        for paginate_call in paginator.paginate.call_args_list:
            assert len(paginate_call.kwargs["Filters"][0]["Values"]) <= 50
            requested_rds_arns.extend(paginate_call.kwargs["Filters"][0]["Values"])

        # assert that all clusters were actually requested
        assert len(requested_rds_arns) == 150
        assert all(
            f"arn:aws:rds:us-east-1:123456789012:db:{instance_id}" in requested_rds_arns
            for instance_id in rds_instances
        )


def test_describe_clusters_respects_50_arn_filter_limit(moto_backend: None) -> None:
    # see ADR-0007
    rds_clusters = create_rds_clusters(150)
    rds_service = build_rds_service()

    with patch.object(rds_service, "_rds_client") as mock_rds_client:
        paginator = MagicMock()
        mock_rds_client.get_paginator.return_value = paginator

        list(rds_service.get_in_scope_rds_clusters())

        paginator.paginate.assert_called()
        requested_rds_arns = []

        # assert that no reqeust exceeded 50 names in the filter
        for paginate_call in paginator.paginate.call_args_list:
            assert len(paginate_call.kwargs["Filters"][0]["Values"]) <= 50
            requested_rds_arns.extend(paginate_call.kwargs["Filters"][0]["Values"])

        # assert that all clusters were actually requested
        assert len(requested_rds_arns) == 150
        assert all(
            f"arn:aws:rds:us-east-1:123456789012:cluster:{instance_id}"
            in requested_rds_arns
            for instance_id in rds_clusters
        )
