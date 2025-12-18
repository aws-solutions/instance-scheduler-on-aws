# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from typing import Any, Mapping
from unittest.mock import Mock

from instance_scheduler.util.custom_resource_waiter import (
    CustomResourceWaiter,
    CustomResourceWaiterResponse,
)


def mock_context() -> Mock:
    context = Mock()
    context.get_remaining_time_in_millis.return_value = 300000
    return context


class ConcreteWaiter(CustomResourceWaiter[Mapping[str, Any]]):
    def _create_request(self) -> CustomResourceWaiterResponse:
        return self.OkResponse()

    def _update_request(self) -> CustomResourceWaiterResponse:
        return self.OkResponse()

    def _delete_request(self) -> CustomResourceWaiterResponse:
        return self.OkResponse()


class TestGetListFromProperties:
    def test_returns_list_when_present(self) -> None:
        waiter = ConcreteWaiter({}, mock_context())
        properties = {"regions": ["us-west-1", "us-east-1", "af-south-1"]}
        result = waiter.purge_empty_strings(properties, "regions")
        assert result == ["us-west-1", "us-east-1", "af-south-1"]

    def test_returns_empty_list_when_attribute_missing(self) -> None:
        waiter = ConcreteWaiter({}, mock_context())
        properties: Mapping[str, Any] = {}
        result = waiter.purge_empty_strings(properties, "regions")
        assert result == []

    def test_returns_empty_list_when_single_empty_string(self) -> None:
        waiter = ConcreteWaiter({}, mock_context())
        properties = {"regions": [""]}
        result = waiter.purge_empty_strings(properties, "regions")
        assert result == []

    def test_returns_list_with_empty_string_when_multiple_elements(self) -> None:
        waiter = ConcreteWaiter({}, mock_context())
        properties = {"regions": ["", "us-east-1"]}
        result = waiter.purge_empty_strings(properties, "regions")
        assert result == ["", "us-east-1"]
