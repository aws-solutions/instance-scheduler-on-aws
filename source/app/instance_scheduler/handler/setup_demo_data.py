# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from instance_scheduler.configuration.config_admin import (
    ConfigTablePeriodItem,
    ConfigTableScheduleItem,
)

PERIOD_WORKING_DAYS = ConfigTablePeriodItem(
    name="working-days",
    description="Working days",
    weekdays={"mon-fri"},
)
PERIOD_WEEKENDS = ConfigTablePeriodItem(
    name="weekends",
    description="Days in weekend",
    weekdays={"sat-sun"},
)
PERIOD_OFFICE_HOURS = ConfigTablePeriodItem(
    name="office-hours",
    description="Office hours",
    weekdays={"mon-fri"},
    begintime="09:00",
    endtime="17:00",
)
PERIOD_FIRST_MONDAY_IN_QUARTER = ConfigTablePeriodItem(
    name="first-monday-in-quarter",
    description="Every first monday of each quarter",
    weekdays={"mon#1"},
    months={"jan/3"},
)

SCHEDULE_SEATTLE_OFFICE_HOURS = ConfigTableScheduleItem(
    name="seattle-office-hours",
    description="Office hours in Seattle (Pacific)",
    periods={"office-hours"},
    timezone="US/Pacific",
)
SCHEDULE_UK_OFFICE_HOURS = ConfigTableScheduleItem(
    name="uk-office-hours",
    description="Office hours in UK",
    periods={"office-hours"},
    timezone="Europe/London",
)
SCHEDULE_STOPPED = ConfigTableScheduleItem(
    name="stopped",
    description="Instances stopped",
    override_status="stopped",
    use_metrics=False,
)
SCHEDULE_RUNNING = ConfigTableScheduleItem(
    name="running",
    description="Instances running",
    override_status="running",
    use_metrics=False,
)
SCHEDULE_SCALING = ConfigTableScheduleItem(
    name="scale-up-down",
    description="Vertical scaling on weekdays, based on UTC time",
    periods={"working-days@t2.micro", "weekends@t2.nano"},
    timezone="UTC",
)
