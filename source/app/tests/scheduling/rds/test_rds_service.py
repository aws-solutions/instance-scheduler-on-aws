# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import os
from contextlib import contextmanager
from typing import Iterator, Sequence
from unittest.mock import MagicMock, call, patch

import pytest
from _pytest.fixtures import fixture
from instance_scheduler.configuration.scheduling_context import SchedulingContext
from instance_scheduler.scheduling.rds.rds import RdsService
from tests.integration.helpers.rds_helpers import (
    create_rds_clusters,
    create_rds_instances,
)
from tests.test_utils.mock_scheduling_request_environment import (
    MockSchedulingRequestEnvironment,
)


def test_rds_service_attributes(scheduling_context: SchedulingContext) -> None:
    service = RdsService(
        scheduling_context=scheduling_context,
        env=MockSchedulingRequestEnvironment(),
    )
    assert service.service_name == "rds"


@fixture
def mock_boto_client() -> Iterator[MagicMock]:
    with patch(
        "instance_scheduler.util.session_manager.AssumedRole.client"
    ) as get_client_func:
        mock = MagicMock()
        get_client_func.return_value = mock

        # Mock paginator for both RDS and RGTA clients
        paginator_mock = MagicMock()
        paginator_mock.paginate.return_value = []
        mock.get_paginator.return_value = paginator_mock

        yield mock


@contextmanager
def mock_get_tagged_resources_function(
    rds_service: RdsService,
    instance_ids: Sequence[str] = [],
    cluster_ids: Sequence[str] = [],
) -> Iterator[None]:

    describe_response = [
        f"arn:aws:rds:us-east-1:123456789012:db:{instance_id}"
        for instance_id in instance_ids
    ] + [
        f"arn:aws:rds:us-east-1:123456789012:cluster:{cluster_id}"
        for cluster_id in cluster_ids
    ]

    with patch.object(
        RdsService,
        "describe_tagged_rds_resource_arns",
        return_value=iter(describe_response),
    ):
        yield


def test_skips_describe_instances_when_no_tagged_instances_found(
    mock_boto_client: MagicMock, scheduling_context: SchedulingContext
) -> None:
    env = MockSchedulingRequestEnvironment(
        enable_rds_service=True,
        enable_rds_clusters=True,
        enable_neptune_service=True,
        enable_docdb_service=True,
    )
    clusters = create_rds_clusters(1)

    rds_service = RdsService(scheduling_context=scheduling_context, env=env)

    with mock_get_tagged_resources_function(rds_service, cluster_ids=clusters):
        list(rds_service.describe_managed_instances())

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
    mock_boto_client: MagicMock, scheduling_context: SchedulingContext
) -> None:
    env = MockSchedulingRequestEnvironment(
        enable_rds_service=True,
        enable_rds_clusters=True,
        enable_neptune_service=True,
        enable_docdb_service=True,
    )
    instances = create_rds_instances(1)
    rds_service = RdsService(scheduling_context=scheduling_context, env=env)

    with mock_get_tagged_resources_function(rds_service, instance_ids=instances):
        list(rds_service.describe_managed_instances())

    # did call instances
    mock_boto_client.get_paginator.assert_has_calls(
        [call("describe_db_instances")],
    )

    # did not call clusters
    with pytest.raises(AssertionError):
        mock_boto_client.get_paginator.assert_has_calls(
            [call("describe_db_clusters")],
        )


def test_describe_instances_respects_50_arn_filter_limit(
    moto_backend: None, scheduling_context: SchedulingContext
) -> None:
    os.environ["MOTO_RDS_SNAPSHOT_LIMIT"] = "200"
    # see ADR-0007
    rds_instances = create_rds_instances(150)
    rds_service = RdsService(
        scheduling_context=scheduling_context, env=MockSchedulingRequestEnvironment()
    )

    with patch(
        "instance_scheduler.util.session_manager.AssumedRole.client"
    ) as mock_client, mock_get_tagged_resources_function(
        rds_service, instance_ids=rds_instances
    ):
        paginator = MagicMock()
        mock_client.return_value.get_paginator.return_value = paginator

        list(rds_service.describe_managed_instances())

        paginator.paginate.assert_called()
        requested_rds_arns = []

        # assert that no request exceeded 50 names in the filter
        for paginate_call in paginator.paginate.call_args_list:
            assert len(paginate_call.kwargs["Filters"][0]["Values"]) <= 50
            requested_rds_arns.extend(paginate_call.kwargs["Filters"][0]["Values"])

        # assert that all instances were actually requested
        assert len(requested_rds_arns) == 150
        assert all(
            f"arn:aws:rds:us-east-1:123456789012:db:{instance_id}" in requested_rds_arns
            for instance_id in rds_instances
        )


def test_describe_clusters_respects_50_arn_filter_limit(
    moto_backend: None, scheduling_context: SchedulingContext
) -> None:
    # see ADR-0007
    rds_clusters = create_rds_clusters(150)
    rds_service = RdsService(
        scheduling_context=scheduling_context, env=MockSchedulingRequestEnvironment()
    )

    with patch(
        "instance_scheduler.util.session_manager.AssumedRole.client"
    ) as mock_client, mock_get_tagged_resources_function(
        rds_service, cluster_ids=rds_clusters
    ):
        paginator = MagicMock()
        mock_client.return_value.get_paginator.return_value = paginator

        list(rds_service.describe_managed_instances())

        paginator.paginate.assert_called()
        requested_rds_arns = []

        # assert that no request exceeded 50 names in the filter
        for paginate_call in paginator.paginate.call_args_list:
            assert len(paginate_call.kwargs["Filters"][0]["Values"]) <= 50
            requested_rds_arns.extend(paginate_call.kwargs["Filters"][0]["Values"])

        # assert that all clusters were actually requested
        assert len(requested_rds_arns) == 150
        assert all(
            f"arn:aws:rds:us-east-1:123456789012:cluster:{cluster_id}"
            in requested_rds_arns
            for cluster_id in rds_clusters
        )
