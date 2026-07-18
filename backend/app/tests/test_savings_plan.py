"""Sparplaner: insättningslogik, kedjade rader, nyckeltal, prognos och API."""
from datetime import date

from sqlalchemy import select

from app.db.models import SavingsAccount, SavingsPlan, SavingsSnapshot
from app.services.savings_plan import (
    deposit_count,
    end_active_plan,
    invested_at,
    upsert_plan,
)


def _mk_account(db, name="ISK", **kw):
    a = SavingsAccount(name=name, asset_class="equity", **kw)
    db.add(a)
    db.flush()
    return a


def _mk_snapshot(db, account_id, snapshot_date, value_ore):
    db.add(
        SavingsSnapshot(
            savings_account_id=account_id, snapshot_date=snapshot_date, value_ore=value_ore
        )
    )
    db.flush()


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


class TestUpsertPlan:
    def test_start_value_from_latest_snapshot(self, db):
        a = _mk_account(db)
        _mk_snapshot(db, a.id, "2026-06-30", 10_000_000)
        plan = upsert_plan(db, a.id, 500_000, "2026-07-01")
        assert plan.start_value_ore == 10_000_000

    def test_start_value_sums_holdings(self, db):
        isk = _mk_account(db)
        fond_a = _mk_account(db, "Fond A", parent_id=isk.id, target_pct=82)
        fond_b = _mk_account(db, "Fond B", parent_id=isk.id, target_pct=18)
        _mk_snapshot(db, fond_a.id, "2026-06-30", 4_100_000)
        _mk_snapshot(db, fond_b.id, "2026-06-30", 900_000)
        plan = upsert_plan(db, isk.id, 500_000, "2026-07-01")
        assert plan.start_value_ore == 5_000_000

    def test_start_value_zero_without_snapshots(self, db):
        a = _mk_account(db)
        plan = upsert_plan(db, a.id, 500_000, "2026-07-01")
        assert plan.start_value_ore == 0

    def test_snapshots_after_start_are_ignored(self, db):
        a = _mk_account(db)
        _mk_snapshot(db, a.id, "2026-06-30", 10_000_000)
        _mk_snapshot(db, a.id, "2026-08-31", 99_000_000)
        plan = upsert_plan(db, a.id, 500_000, "2026-07-01")
        assert plan.start_value_ore == 10_000_000

    def test_invested_accumulates_monthly(self, db):
        a = _mk_account(db)
        _mk_snapshot(db, a.id, "2026-06-30", 10_000_000)
        upsert_plan(db, a.id, 500_000, "2026-07-01")
        rows = list(db.scalars(select(SavingsPlan)))
        # insättningar 1 jul, 1 aug, 1 sep = 3 st
        assert invested_at(rows, date(2026, 9, 1)) == 10_000_000 + 3 * 500_000
        assert invested_at(rows, date(2026, 6, 30)) is None

    def test_amount_change_chains_rows(self, db):
        a = _mk_account(db)
        upsert_plan(db, a.id, 500_000, "2026-01-15")
        upsert_plan(db, a.id, 600_000, "2026-04-01")
        rows = list(db.scalars(select(SavingsPlan)))
        old = next(r for r in rows if r.monthly_amount_ore == 500_000)
        new = next(r for r in rows if r.monthly_amount_ore == 600_000)
        assert old.end_date == "2026-03-31"
        # insatt vid bytet: 3 insättningar (15 jan, 15 feb, 15 mar)
        assert new.start_value_ore == 3 * 500_000
        assert invested_at(rows, date(2026, 4, 1)) == 3 * 500_000 + 600_000

    def test_same_day_replace_removes_old_row(self, db):
        a = _mk_account(db)
        _mk_snapshot(db, a.id, "2026-06-30", 10_000_000)
        upsert_plan(db, a.id, 500_000, "2026-07-01")
        upsert_plan(db, a.id, 700_000, "2026-07-01")
        rows = list(db.scalars(select(SavingsPlan)))
        assert len(rows) == 1
        assert rows[0].monthly_amount_ore == 700_000
        assert rows[0].start_value_ore == 10_000_000

    def test_end_active_plan(self, db):
        a = _mk_account(db)
        upsert_plan(db, a.id, 500_000, "2026-01-15")
        assert end_active_plan(db, a.id, date(2026, 7, 18)) is True
        rows = list(db.scalars(select(SavingsPlan)))
        assert rows[0].end_date == "2026-07-18"
        # insatt kapital fryses efter avslut
        assert invested_at(rows, date(2026, 12, 1)) == invested_at(rows, date(2026, 7, 18))
        assert end_active_plan(db, a.id, date(2026, 7, 19)) is False
