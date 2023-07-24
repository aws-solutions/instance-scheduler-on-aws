# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from collections.abc import Mapping as _Mapping
from typing import Any as _Any
from typing import Final as _Final

from .base import Service, ServiceArgs
from .ec2 import Ec2Service
from .rds import RdsService

services: _Final[_Mapping[str, type[Service[_Any]]]] = {
    "ec2": Ec2Service,
    "rds": RdsService,
}

__all__ = [
    "Ec2Service",
    "Service",
    "ServiceArgs",
    "services",
    "RdsService",
]
