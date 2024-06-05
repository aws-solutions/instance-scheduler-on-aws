# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import datetime
import re
import time

TIME_FORMAT = "HH:MM"
"""human-readable time format that can be displayed to users if an input fails is_valid_time_str"""


def is_valid_time_str(timestr: str) -> bool:
    """
    verify that a string matches the time format expected by parse_time_str

    a human-readable representation of a valid time_format can be accessed as TIME_FORMAT
    """
    return re.match(r"^([0|1]?\d|2[0-3]):[0-5]\d$", timestr) is not None


def parse_time_str(timestr: str) -> datetime.time:
    """
    Standardised method to build time object instance from time string
    :param timestr: string in format as defined in configuration.TIME_FORMAT_STRING
    :return: time object from time string, None if the time is invalid
    """
    try:
        tm = time.strptime(timestr, "%H:%M")
    except ValueError:
        raise ValueError(f"Invalid time string {timestr}, must match {TIME_FORMAT}")
    return datetime.time(tm.tm_hour, tm.tm_min, 0)
