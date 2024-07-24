# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
class AppEnvError(RuntimeError):
    pass


def env_to_bool(value: str) -> bool:
    return value.strip().lower() in {"true", "yes"}


def env_to_list(value: str) -> list[str]:
    items = []
    for item in value.split(","):
        stripped = item.strip()
        if stripped:
            items.append(stripped)
    return items
