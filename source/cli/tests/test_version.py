# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from importlib.metadata import version

from instance_scheduler_cli import __version__


def test_version_correctly_picked_up_from_toml() -> None:
    assert __version__ == version("instance_scheduler_cli")
