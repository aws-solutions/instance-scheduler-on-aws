# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from unittest.mock import ANY, MagicMock, patch

from instance_scheduler.util.session_manager import assume_role


@patch("instance_scheduler.util.session_manager.Session")
def test_uses_regional_sts_endpoint(
    mock_session: MagicMock,
) -> None:
    # When assuming a role with sts, if the spoke account does not have the same region enabled as the calling region
    # in sts, the assume will fail. To get around this, the IG requires that customers install the hub and spoke stacks
    # in the same region (ensuring that the region is enabled in both accounts), as such all sts calls should use this
    # local region to ensure proper cross-account, cross-region behavior (at time of writing, the local endpoints return
    # a V2 token which is valid in all regions, the global endpoint returns
    # a V1 token which is only valid in default regions)
    mock_client = MagicMock()
    mock_session.return_value.client = mock_client
    region_name = "executing-region"
    mock_session.return_value.region_name = region_name

    assume_role(account="111122223333", region="us-west-2", role_name="my-role-name")

    mock_client.assert_called_once_with(
        "sts",
        region_name=region_name,
        endpoint_url=f"https://sts.{region_name}.amazonaws.com",
        config=ANY,
    )


@patch("instance_scheduler.util.session_manager.Session")
def test_uses_correct_domain_in_china(
    mock_session: MagicMock,
) -> None:
    region_name = "cn-north-1"

    mock_client = MagicMock()
    mock_session.return_value.client = mock_client
    mock_session.return_value.region_name = region_name
    mock_session.return_value.get_partition_for_region.return_value = "aws-cn"

    assume_role(
        account="111122223333", region="cn-northwest-2", role_name="my-role-name"
    )

    mock_client.assert_called_once_with(
        "sts",
        region_name=region_name,
        endpoint_url=f"https://sts.{region_name}.amazonaws.com.cn",
        config=ANY,
    )
