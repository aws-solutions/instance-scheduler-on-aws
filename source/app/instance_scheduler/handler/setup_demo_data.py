# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from instance_scheduler.model.period_definition import PeriodDefinition
from instance_scheduler.model.period_identifier import PeriodIdentifier
from instance_scheduler.model.schedule_definition import ScheduleDefinition

DEMO_PERIODS = [
    PeriodDefinition(
        name="working-days",
        description="Working days",
        weekdays={"mon-fri"},
    ),
    PeriodDefinition(
        name="weekends",
        description="Days in weekend",
        weekdays={"sat-sun"},
    ),
    PeriodDefinition(
        name="office-hours",
        description="Office hours",
        weekdays={"mon-fri"},
        begintime="09:00",
        endtime="17:00",
    ),
    PeriodDefinition(
        name="first-monday-in-quarter",
        description="Every first monday of each quarter",
        weekdays={"mon#1"},
        months={"jan/3"},
    ),
]

DEMO_SCHEDULES = [
    ScheduleDefinition(
        name="seattle-office-hours",
        description="Office hours in Seattle (Pacific)",
        periods=[PeriodIdentifier("office-hours")],
        timezone="US/Pacific",
    ),
    ScheduleDefinition(
        name="uk-office-hours",
        description="Office hours in UK",
        periods=[PeriodIdentifier("office-hours")],
        timezone="Europe/London",
    ),
    ScheduleDefinition(
        name="stopped",
        description="Instances stopped",
        override_status="stopped",
    ),
    ScheduleDefinition(
        name="running",
        description="Instances running",
        override_status="running",
    ),
    ScheduleDefinition(
        name="scale-up-down",
        description="Vertical scaling on weekdays, based on UTC time",
        periods=[
            PeriodIdentifier.of("weekends", "t2.nano"),
            PeriodIdentifier.of("working-days", "t2.micro"),
        ],
        timezone="UTC",
    ),
]
