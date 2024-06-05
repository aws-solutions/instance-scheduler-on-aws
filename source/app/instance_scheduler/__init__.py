# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import tomllib
from pathlib import Path

__version__ = "unknown"

pyproject_toml_file_path = Path(__file__, "../../pyproject.toml").resolve()
if pyproject_toml_file_path.exists() and pyproject_toml_file_path.is_file():
    with open(pyproject_toml_file_path, "rb") as file:
        __version__ = tomllib.load(file)["tool"]["poetry"]["version"]
