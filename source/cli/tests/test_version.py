# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

from instance_scheduler_cli import __version__


def test_version_correctly_picked_up_from_toml():
    assert __version__ == "1.5.0"
