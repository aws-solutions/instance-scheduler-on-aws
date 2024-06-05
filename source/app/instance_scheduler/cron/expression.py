# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
The class hierarchy defined in this module is a high-level representation of the fields
of a cron expression. A cron expression is a string that defines the recurrence for a
job executed by the cron daemon, a job scheduler on *nix distributions.

A cron expression most commonly takes the form of:

    <minute> <hour> <day_of_month> <month_of_year> <day_of_week> <command>

cron expressions are not defined by a standard, so the specific supported features as
well as the exact behavior of features will differ depending on the implementation. The
form of the expression may differ as well.

Default features supported by most implementations include:

- names instead of integer values for months and weekdays
- ranges (e.g. 4-6, Mon-Fri)
- steps (e.g. */2, or every other day/month)

Extensions supported by many implementations include:

- wildcard for last day (L)
- wildcard for nth weekday (e.g. Mon#3, or the third Monday of the month)
- wildcard for nearest weekday (e.g. 13W, or the nearest weekday to the 13th)

Deviations from the above definition include:

- additional seconds field at the beginning of the expression
- additional years field at the end of the expression
- combinations of different expressions separated by commas

The specific features supported and the behavior of the features for each field differ
depending on the specific implementation. This class hierarchy is intended to be an
abstract representation of an expression as defined by the user. An expression can exist
independent of it being used as a day-of-month or day-of-week field, but certain
features only make sense for certain fields (e.g. nearest weekday).

As an example, consider the expression "1-5/2". This expression should be parsed as "a
step starting on the first value, repeating every two iterations, stopping at the fifth
value". This expression could be resolved equally well as a day-of-month field meaning
the first of the month, the third of the month, and the fifth of the month, or as a
day-of-week field meaning Monday, Wednesday, and Friday[1].

The intended use of this class hierarchy is for it to be produced by a parser that may
or may not have knowledge of the specific field being parsed or the specific
implementation where the expression was defined. After parsing, the expression retains
no semantic meaning specific to the field or implementation. Optionally, a validator
that does have knowledge of the specific field and/or implementation can decide if the
expression conforms to the expected feature set and behavior for the field or
implementation. Finally, the business logic is implemented with knowledge of the feature
set supported by the target implementation.

As a simple example, consider the expression "?" as a day-of-week field value. Parsing
the expression should result in an "all values" representation. Validation confirms that
this meaning is correct for a day-of-week field in an Instance Scheduler period
definition. The business logic is to translate this expression to a recurrence string
for AutoScaling Groups. The day-of-week field for ASGs supports the "all values"
feature, but it only uses the asterisk wildcard. The output of the conversion to ASG
day-of-week recurrence string will be "*".

[1] Though most cron implementations use the value one to mean Monday in a day-of-week
field, Instance Scheduler was implemented with the value zero meaning Monday, which
corresponds to the values in the Python `calendar` package.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class CronUnion:
    """The union of multiple other expressions, typically represented by a
    comma-separated list"""

    exprs: tuple["CronExpression", ...]


@dataclass(frozen=True)
class CronAll:
    """All values"""


@dataclass(frozen=True)
class CronSingleValueNumeric:
    """A single numeric value"""

    value: int


@dataclass(frozen=True)
class CronSingleValueLast:
    """The last possible value"""


@dataclass(frozen=True)
class CronNearestWeekday:
    """The weekday nearest the specified value"""

    value: CronSingleValueNumeric


@dataclass(frozen=True)
class CronNthWeekday:
    """The nth occurence of the specified weekday in a month"""

    day: CronSingleValueNumeric
    n: int


@dataclass(frozen=True)
class CronLastWeekday:
    """The last occurence of the specified weekday in a month"""

    day: CronSingleValueNumeric


@dataclass(frozen=True)
class CronRange:
    """A range of values beginning at `start`, repeating every `interval` values, up to
    and including `end`. `start` may be after `end`, in which case the range wraps if
    allowed."""

    start: CronSingleValueNumeric
    end: CronSingleValueNumeric | CronSingleValueLast | None = None
    interval: int = 1


CronExpression = (
    CronUnion
    | CronAll
    | CronSingleValueNumeric
    | CronSingleValueLast
    | CronNearestWeekday
    | CronNthWeekday
    | CronLastWeekday
    | CronRange
)
"""A union type for the possible values of an arbitrary cron expression"""


@dataclass(frozen=True)
class FullCronExpression:
    """A cron recurrence expression for days and months, but not time of day"""

    days_of_month: CronExpression
    months_of_year: CronExpression
    days_of_week: CronExpression
