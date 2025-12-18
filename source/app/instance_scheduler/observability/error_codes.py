# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from enum import Enum


class ErrorCode(str, Enum):
    UNKNOWN_SCHEDULE = "UnknownSchedule"
    UNSUPPORTED_RESOURCE = "UnsupportedResource"
    INCOMPATIBLE_SCHEDULE = "IncompatibleSchedule"
    START_FAILED = "StartFailed"
    STOP_FAILED = "StopFailed"
    CONFIGURATION_FAILED = "ConfigurationFailed"
    UNKNOWN_ERROR = "UnknownError"
