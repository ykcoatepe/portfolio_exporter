import unittest
from datetime import datetime, timedelta

import option_chain_snapshot as oc

class ChooseExpiryTests(unittest.TestCase):
    def test_weekly_within_seven_days(self):
        today = datetime.utcnow().date()
        exp_close = (today + timedelta(days=3)).strftime('%Y%m%d')
        exp_later = (today + timedelta(days=10)).strftime('%Y%m%d')
        result = oc.choose_expiry([exp_close, exp_later])
        self.assertEqual(result, exp_close)

    def test_first_friday(self):
        today = datetime.utcnow().date()
        # choose a date more than 7 days ahead that is a Friday
        days = 8
        while (today + timedelta(days=days)).weekday() != 4:
            days += 1
        friday = (today + timedelta(days=days)).strftime('%Y%m%d')
        other = (today + timedelta(days=days+2)).strftime('%Y%m%d')
        result = oc.choose_expiry([other, friday])
        self.assertEqual(result, friday)

if __name__ == '__main__':
    unittest.main()
