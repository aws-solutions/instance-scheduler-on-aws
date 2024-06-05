# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from dataclasses import dataclass

from instance_scheduler.service.abstract_instance import AbstractInstance


@dataclass(kw_only=True)
class RdsInstance(AbstractInstance):
    _is_cluster: bool
    _arn: str
    _engine_type: str

    @property
    def display_str(self) -> str:
        s = f"RDS:{self._engine_type}:{self.id}"
        if self.name:
            s += " ({})".format(self.name)
        return s

    @property
    def arn(self) -> str:
        return self._arn

    @property
    def is_cluster(self) -> bool:
        return self._is_cluster

    @property
    def is_schedulable(self) -> bool:
        return self._current_state in ["available", "stopped"]

    @property
    def is_running(self) -> bool:
        return self._current_state == "available"

    @property
    def is_stopped(self) -> bool:
        return self._current_state == "stopped"

    @property
    def is_resizable(self) -> bool:
        return False
