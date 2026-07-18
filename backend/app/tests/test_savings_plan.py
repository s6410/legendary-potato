"""Sparplaner: insättningslogik, kedjade rader, nyckeltal, prognos och API."""
from datetime import date

from app.services.savings_plan import deposit_count


class TestDepositCount:
    def test_first_deposit_on_start_date(self):
        assert deposit_count(date(2026, 7, 18), date(2026, 7, 18)) == 1

    def test_second_deposit_next_month_same_day(self):
        assert deposit_count(date(2026, 7, 18), date(2026, 8, 17)) == 1
        assert deposit_count(date(2026, 7, 18), date(2026, 8, 18)) == 2

    def test_month_end_clamping(self):
        # start 31 jan: februari-insättningen sker den 28:e (klampas)
        assert deposit_count(date(2026, 1, 31), date(2026, 2, 27)) == 1
        assert deposit_count(date(2026, 1, 31), date(2026, 2, 28)) == 2
        assert deposit_count(date(2026, 1, 31), date(2026, 3, 30)) == 2
        assert deposit_count(date(2026, 1, 31), date(2026, 3, 31)) == 3

    def test_before_start_is_zero(self):
        assert deposit_count(date(2026, 7, 18), date(2026, 7, 17)) == 0

    def test_leap_year_february(self):
        assert deposit_count(date(2027, 12, 31), date(2028, 2, 29)) == 3
