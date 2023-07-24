# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from collections.abc import Iterator
from os import scandir
from pathlib import Path

optional_shebang = "#!/usr/bin/env python"

header_lines = [
    "# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.",
    "# SPDX-License-Identifier: Apache-2.0",
]


def valid_header(path: Path) -> bool:
    header_length = len(header_lines)
    lines = []
    with open(path) as f:
        for _ in range(header_length + 1):
            lines.append(f.readline())
    line_index = 0
    if lines[0].strip() == optional_shebang:
        line_index = 1
    for header_line in header_lines:
        if lines[line_index].strip() != header_line:
            return False
        line_index += 1
    return True


exclude_dirs = {".tox", ".mypy_cache"}


def python_source_files(path: str) -> Iterator[Path]:
    for file in Path(path).glob("*.py"):
        if file.stat().st_size > 0:
            yield file
    for entry in scandir(path):
        if entry.is_dir() and entry.name not in exclude_dirs:
            yield from python_source_files(entry.path)


def test_headers_exist() -> None:
    for file_path in python_source_files("."):
        assert valid_header(
            file_path
        ), f"{file_path} does not contain a valid copyright header"
