import calendar
import unittest

from configuration.setbuilders.monthday_setbuilder import MonthdaySetBuilder


class TestMonthdaySetBuilder(unittest.TestCase):
    def test_name(self):
        years = [2016, 2017]  # leap and normal year

        for year in years:
            for month in range(1, 13):
                _, days = calendar.monthrange(year, month)

                for day in range(1, days):
                    self.assertEquals(MonthdaySetBuilder(year, month).build(str(day)), {day})

    def test_L_wildcard(self):
        years = [2016, 2017]  # leap and normal year

        for year in years:
            for month in range(1, 13):
                _, days = calendar.monthrange(year, month)
                self.assertEquals(MonthdaySetBuilder(year, month).build("L"), {days})

    def test_W_wildcard(self):
        years = [2016, 2017]  # leap and normal year

        for year in years:
            for month in range(1, 13):
                _, days = calendar.monthrange(year, month)

                for day in range(1, days):
                    weekday = calendar.weekday(year, month, day)
                    result = day
                    if weekday == 5:
                        result = day - 1 if day > 1 else day + 2
                    elif weekday == 6:
                        result = day + 1 if day < days else day - 2

                    self.assertEquals(MonthdaySetBuilder(year, month).build(str(day) + "W"), {result})

    def test_exceptions(self):
        for h in range(13, 25):
            self.assertRaises(ValueError, MonthdaySetBuilder(2016, 1).build, "W")
            self.assertRaises(ValueError, MonthdaySetBuilder(2016, 1).build, "32W")
