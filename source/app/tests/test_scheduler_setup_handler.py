# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

from requesthandlers.scheduler_setup_handler import SchedulerSetupHandler


def test_a_valid_org_id_pattern():
    handler = SchedulerSetupHandler(
        {"ResourceProperties": {"stack_version": "test"}}, {}
    )
    response = handler.is_valid_org_id("o-x1mhq1lvsr")
    assert response != None


def test_an_invalid_org_id_pattern():
    handler = SchedulerSetupHandler(
        {"ResourceProperties": {"stack_version": "test"}}, {}
    )
    response = handler.is_valid_org_id("111111111111,222222222222")
    assert response == None
