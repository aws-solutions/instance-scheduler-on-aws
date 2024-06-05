# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from importlib.metadata import version

from instance_scheduler import __version__


def test_version_read_from_toml_matches_package_version() -> None:
    assert version("instance_scheduler") == __version__
