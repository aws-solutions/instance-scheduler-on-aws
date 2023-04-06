# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

from instance_scheduler.requesthandlers.scheduler_setup_handler import SchedulerSetupHandler
from unittest import mock
from unittest.mock import MagicMock


def test_a_valid_org_id_pattern():
    handler = SchedulerSetupHandler(
        {"ResourceProperties": {"stack_version": "test"}}, {}
    )
    response = handler.get_valid_org_id("o-x1mhq1lvsr")
    assert response != "o-x1mhq1lvsr"


def test_an_invalid_org_id_pattern():
    handler = SchedulerSetupHandler(
        {"ResourceProperties": {"stack_version": "test"}}, {}
    )
    response = handler.get_valid_org_id("111111111111,222222222222")
    assert response == None
