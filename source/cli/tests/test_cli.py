# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from unittest.mock import patch

from cli_test_helpers import shell


def test_cli_entrypoint_exists():
    result = shell("scheduler-cli --help")
    assert result.exit_code == 0


def test_calling_with_no_args_exits_gracefully():
    result = shell("scheduler-cli")
    assert result.exit_code == 0
