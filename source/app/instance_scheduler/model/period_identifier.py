# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from typing import Optional


class PeriodIdentifier(str):
    @property
    def name(self) -> str:
        return self.split("@")[0]

    @property
    def desired_type(self) -> Optional[str]:
        tokens = self.split("@")
        if len(tokens) > 1:
            return tokens[1]
        else:
            return None

    @classmethod
    def of(
        cls, period_name: str, instance_type: Optional[str] = None
    ) -> "PeriodIdentifier":
        if instance_type:
            return PeriodIdentifier(f"{period_name}@{instance_type}")
        else:
            return PeriodIdentifier(period_name)
