# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

from requesthandlers.scheduler_setup_handler import SchedulerSetupHandler
from unittest import mock
from unittest.mock import MagicMock


def test_a_valid_org_id_pattern():
    handler = SchedulerSetupHandler(
        {"ResourceProperties": {"stack_version": "test"}}, {}
    )
    response = handler.is_valid_org_id("o-x1mhq1lvsr")
    assert response != "o-x1mhq1lvsr"


def test_an_invalid_org_id_pattern():
    handler = SchedulerSetupHandler(
        {"ResourceProperties": {"stack_version": "test"}}, {}
    )
    response = handler.is_valid_org_id("111111111111,222222222222")
    assert response == None


# def test_custom_update():
#     with mock.patch(
#         "configuration.config_admin.update_config", new_callable=mock.PropertyMock
#     ) as mock_update_config:
#         mock_update_config.return_value = None
#         handler = SchedulerSetupHandler(
#             {"ResourceProperties": {"stack_version": "test"}}, {}
#         )
#         handler.remote_account_ids = "o-x1mhq1lvsr"
#         handler.use_aws_organizations = "True"
#         response = handler._update_settings(prev_org_remote_account_ids=None)
#         assert response == False
