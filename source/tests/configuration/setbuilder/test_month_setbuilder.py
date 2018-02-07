import calendar
import unittest

from configuration.setbuilders.month_setbuilder import MonthSetBuilder


class TestMonthSetBuilder(unittest.TestCase):
    def test_name(self):
        # abbreviations
        for i, name in enumerate(calendar.month_abbr[1:]):
            self.assertEquals(MonthSetBuilder().build(name), {i + 1})
            self.assertEquals(MonthSetBuilder().build(name.lower()), {i + 1})
            self.assertEquals(MonthSetBuilder().build(name.upper()), {i + 1})

        # full names
        for i, name in enumerate(calendar.month_name[1:]):
            self.assertEquals(MonthSetBuilder().build(name), {i + 1})
            self.assertEquals(MonthSetBuilder().build(name.lower()), {i + 1})
            self.assertEquals(MonthSetBuilder().build(name.upper()), {i + 1})

    def test_value(self):
        for i in range(1, 12):
            self.assertEquals(MonthSetBuilder().build(str(i)), {i})
