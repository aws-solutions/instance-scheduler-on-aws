# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import subprocess


def test_run_as_module() -> None:
    result = subprocess.run(
        ["python", "-m", "instance_scheduler_cli", "--version"],
        stdout=subprocess.DEVNULL,
    )
    assert result.stderr is None


def test_calling_with_no_args_exits_gracefully() -> None:
    result = subprocess.run(
        [
            "python",
            "-m",
            "instance_scheduler_cli",
        ],
        stdout=subprocess.DEVNULL,
    )
    assert result.stderr is None
