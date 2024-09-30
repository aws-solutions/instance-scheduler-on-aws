# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import json
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from _pytest.python_api import raises

from instance_scheduler.configuration.instance_schedule import InstanceSchedule
from instance_scheduler.configuration.running_period import RunningPeriod
from instance_scheduler.cron.cron_recurrence_expression import CronRecurrenceExpression
from instance_scheduler.handler.cli.schedule_usage import (
    CliCustomEncoder,
    get_schedule_usage,
)


def test_custom_encoder_set() -> None:
    """Stringifies set as list"""
    assert json.dumps(set(), cls=CliCustomEncoder) == "[]"

    items = [1, 2, 3]
    items_set = set(items)
    result = json.loads(json.dumps(items_set, cls=CliCustomEncoder))
    assert isinstance(result, list)
    assert items_set == set(result)


def test_custom_encoder_datetime() -> None:
    """Stringifies datetimes in locale format without seconds"""
    dt_with_seconds = datetime(
        year=2023, month=5, day=11, hour=11, minute=41, second=20
    )
    dt_no_seconds = dt_with_seconds.replace(second=0)
    expected_str = f'"{dt_no_seconds.strftime("%x %X")}"'
    assert json.dumps(dt_with_seconds, cls=CliCustomEncoder) == expected_str


def test_custom_encoder_invalid() -> None:
    """Errors on other types"""
    with raises(TypeError):
        json.dumps(date(year=2023, month=1, day=12), cls=CliCustomEncoder)


def test_describe_schedule_describes_simple_schedule() -> None:
    schedule = InstanceSchedule(
        name="test-schedule",
        timezone=ZoneInfo("UTC"),
        periods=[
            {
                "period": RunningPeriod(
                    name="test-period",
                    begintime=time(7, 0, 0),
                    endtime=time(15, 0, 0),
                )
            }
        ],
    )

    output_json = get_schedule_usage(
        schedule, start=datetime(2024, 3, 1), end=datetime(2024, 3, 5)
    )
    assert output_json == {
        "schedule": "test-schedule",
        "usage": {
            "2024-03-01": {
                "billing_hours": 8,
                "billing_seconds": 28800,
                "running_periods": {
                    "test-period": {
                        "begin": "03/01/24 " "07:00:00",
                        "billing_hours": 8,
                        "billing_seconds": 28800,
                        "end": "03/01/24 " "15:00:00",
                    }
                },
            },
            "2024-03-02": {
                "billing_hours": 8,
                "billing_seconds": 28800,
                "running_periods": {
                    "test-period": {
                        "begin": "03/02/24 " "07:00:00",
                        "billing_hours": 8,
                        "billing_seconds": 28800,
                        "end": "03/02/24 " "15:00:00",
                    }
                },
            },
            "2024-03-03": {
                "billing_hours": 8,
                "billing_seconds": 28800,
                "running_periods": {
                    "test-period": {
                        "begin": "03/03/24 " "07:00:00",
                        "billing_hours": 8,
                        "billing_seconds": 28800,
                        "end": "03/03/24 " "15:00:00",
                    }
                },
            },
            "2024-03-04": {
                "billing_hours": 8,
                "billing_seconds": 28800,
                "running_periods": {
                    "test-period": {
                        "begin": "03/04/24 " "07:00:00",
                        "billing_hours": 8,
                        "billing_seconds": 28800,
                        "end": "03/04/24 " "15:00:00",
                    }
                },
            },
            "2024-03-05": {
                "billing_hours": 8,
                "billing_seconds": 28800,
                "running_periods": {
                    "test-period": {
                        "begin": "03/05/24 " "07:00:00",
                        "billing_hours": 8,
                        "billing_seconds": 28800,
                        "end": "03/05/24 " "15:00:00",
                    }
                },
            },
        },
    }


def test_describe_schedule_uses_correctly_handles_nth_weekday() -> None:
    schedule = InstanceSchedule(
        name="test-schedule",
        timezone=ZoneInfo("UTC"),
        periods=[
            {
                "period": RunningPeriod(
                    name="test-period",
                    cron_recurrence=CronRecurrenceExpression.parse(weekdays={"Mon#1"}),
                )
            }
        ],
    )

    output_json = get_schedule_usage(
        schedule, start=datetime(2024, 3, 1), end=datetime(2024, 3, 31)
    )
    assert output_json == {
        "schedule": "test-schedule",
        "usage": {
            "2024-03-01": {
                "billing_hours": 0,
                "billing_seconds": 0,
                "running_periods": {},
            },
            "2024-03-02": {
                "billing_hours": 0,
                "billing_seconds": 0,
                "running_periods": {},
            },
            "2024-03-03": {
                "billing_hours": 0,
                "billing_seconds": 0,
                "running_periods": {},
            },
            "2024-03-04": {
                "billing_hours": 24,
                "billing_seconds": 86400,
                "running_periods": {
                    "test-period": {
                        "begin": "03/04/24 " "00:00:00",
                        "billing_hours": 24,
                        "billing_seconds": 86400,
                        "end": "03/05/24 " "00:00:00",
                    }
                },
            },
            "2024-03-05": {
                "billing_hours": 0,
                "billing_seconds": 0,
                "running_periods": {},
            },
            "2024-03-06": {
                "billing_hours": 0,
                "billing_seconds": 0,
                "running_periods": {},
            },
            "2024-03-07": {
                "billing_hours": 0,
                "billing_seconds": 0,
                "running_periods": {},
            },
            "2024-03-08": {
                "billing_hours": 0,
                "billing_seconds": 0,
                "running_periods": {},
            },
            "2024-03-09": {
                "billing_hours": 0,
                "billing_seconds": 0,
                "running_periods": {},
            },
            "2024-03-10": {
                "billing_hours": 0,
                "billing_seconds": 0,
                "running_periods": {},
            },
            "2024-03-11": {
                "billing_hours": 0,
                "billing_seconds": 0,
                "running_periods": {},
            },
            "2024-03-12": {
                "billing_hours": 0,
                "billing_seconds": 0,
                "running_periods": {},
            },
            "2024-03-13": {
                "billing_hours": 0,
                "billing_seconds": 0,
                "running_periods": {},
            },
            "2024-03-14": {
                "billing_hours": 0,
                "billing_seconds": 0,
                "running_periods": {},
            },
            "2024-03-15": {
                "billing_hours": 0,
                "billing_seconds": 0,
                "running_periods": {},
            },
            "2024-03-16": {
                "billing_hours": 0,
                "billing_seconds": 0,
                "running_periods": {},
            },
            "2024-03-17": {
                "billing_hours": 0,
                "billing_seconds": 0,
                "running_periods": {},
            },
            "2024-03-18": {
                "billing_hours": 0,
                "billing_seconds": 0,
                "running_periods": {},
            },
            "2024-03-19": {
                "billing_hours": 0,
                "billing_seconds": 0,
                "running_periods": {},
            },
            "2024-03-20": {
                "billing_hours": 0,
                "billing_seconds": 0,
                "running_periods": {},
            },
            "2024-03-21": {
                "billing_hours": 0,
                "billing_seconds": 0,
                "running_periods": {},
            },
            "2024-03-22": {
                "billing_hours": 0,
                "billing_seconds": 0,
                "running_periods": {},
            },
            "2024-03-23": {
                "billing_hours": 0,
                "billing_seconds": 0,
                "running_periods": {},
            },
            "2024-03-24": {
                "billing_hours": 0,
                "billing_seconds": 0,
                "running_periods": {},
            },
            "2024-03-25": {
                "billing_hours": 0,
                "billing_seconds": 0,
                "running_periods": {},
            },
            "2024-03-26": {
                "billing_hours": 0,
                "billing_seconds": 0,
                "running_periods": {},
            },
            "2024-03-27": {
                "billing_hours": 0,
                "billing_seconds": 0,
                "running_periods": {},
            },
            "2024-03-28": {
                "billing_hours": 0,
                "billing_seconds": 0,
                "running_periods": {},
            },
            "2024-03-29": {
                "billing_hours": 0,
                "billing_seconds": 0,
                "running_periods": {},
            },
            "2024-03-30": {
                "billing_hours": 0,
                "billing_seconds": 0,
                "running_periods": {},
            },
            "2024-03-31": {
                "billing_hours": 0,
                "billing_seconds": 0,
                "running_periods": {},
            },
        },
    }
