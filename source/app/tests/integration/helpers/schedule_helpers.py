# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import datetime


def at_time(
    time: datetime.time, date: datetime.date = datetime.date(2023, 5, 31)
) -> datetime.datetime:
    return datetime.datetime.combine(date, time, datetime.timezone.utc)


def quick_time(hrs: int, minutes: int, seconds: int) -> datetime.datetime:
    return at_time(datetime.time(hrs, minutes, seconds))
