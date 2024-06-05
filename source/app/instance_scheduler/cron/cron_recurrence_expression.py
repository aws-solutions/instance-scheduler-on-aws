# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from instance_scheduler.cron.cron_to_running_period import (
    monthday_cron_expr_contains,
    months_cron_expr_contains,
    weekday_cron_expr_contains,
)
from instance_scheduler.cron.expression import CronAll, CronExpression
from instance_scheduler.cron.parser import (
    parse_monthdays_expr,
    parse_months_expr,
    parse_weekdays_expr,
)


@dataclass(frozen=True)
class CronRecurrenceExpression:
    """A cron recurrence expression for days and months, but not time of day"""

    monthdays: CronExpression = CronAll()
    months: CronExpression = CronAll()
    weekdays: CronExpression = CronAll()

    def to_asg_scheduled_action(self) -> Any:
        raise NotImplementedError

    @classmethod
    def parse(
        cls,
        *,
        monthdays: set[str] = {"*"},
        months: set[str] = {"*"},
        weekdays: set[str] = {"*"},
    ) -> "CronRecurrenceExpression":
        return CronRecurrenceExpression(
            monthdays=parse_monthdays_expr(monthdays),
            months=parse_months_expr(months),
            weekdays=parse_weekdays_expr(weekdays),
        )

    def contains(self, dt: datetime) -> bool:
        """Does `dt` satisfy the recurrence defined in `expr`"""
        # When both days-of-month and days-of-week are specified, the normal behavior for
        # cron is to trigger on a day that satisfies either expression. However, Instance
        # Scheduler has historically checked that a date satisfies all fields. If a field is
        # missing from the period definition, it is considered satisfied. This means that if
        # a running period is not missing (`None`) and not a wildcard for all values, only
        # days that satisfy the intersection of days-of-month and days-of-week satisfy the
        # expression. This is a departure from standard cron behavior that may surprise
        # customers.
        return all(
            (
                monthday_cron_expr_contains(self.monthdays, dt),
                months_cron_expr_contains(self.months, dt),
                weekday_cron_expr_contains(self.weekdays, dt),
            )
        )
