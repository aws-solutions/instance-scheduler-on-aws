# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from enum import Enum


class InformationalTagKey(str, Enum):
    MANAGED_BY = "IS-ManagedBy"
    ERROR = "IS-Error"
    ERROR_MESSAGE = "IS-ErrorMessage"
    LAST_ACTION = "IS-LastAction"


class ControlTagKey(str, Enum):
    PREFERRED_INSTANCE_TYPES = "IS-PreferredInstanceTypes"
    MIN_DESIRED_MAX = "IS-MinDesiredMax"
