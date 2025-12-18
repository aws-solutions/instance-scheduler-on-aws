# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from typing import TypedDict

IceRetryRequest = TypedDict(
    "IceRetryRequest",
    {
        "account": str,
        "region": str,
        "instance_id": str,
        "preferred_instance_types": list[str],
    },
    total=False,
)
