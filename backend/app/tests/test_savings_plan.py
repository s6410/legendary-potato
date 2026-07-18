"""Sparplaner: insättningslogik, kedjade rader, nyckeltal, prognos och API."""
from datetime import date

from sqlalchemy import select

from app.db.models import SavingsAccount, SavingsPlan, SavingsSnapshot
from app.services.savings_plan import (
    _forecast_series,
    deposit_count,
    end_active_plan,
    invested_at,
    plan_summary,
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


def _create_account(client, name, **extra):
    r = client.post("/api/savings/accounts", json={"name": name, "asset_class": "equity", **extra})
    assert r.status_code == 201, r.text
    return r.json()["id"]


class TestPlanApi:
    def test_put_creates_plan(self, client):
        isk = _create_account(client, "ISK")
        r = client.put(f"/api/savings/accounts/{isk}/plan", json={"monthly_amount_ore": 500_000})
        assert r.status_code == 200, r.text
        assert "id" in r.json()

    def test_plan_on_holding_rejected(self, client):
        isk = _create_account(client, "ISK")
        fond = _create_account(client, "Fond", parent_id=isk, target_pct=100)
        r = client.put(f"/api/savings/accounts/{fond}/plan", json={"monthly_amount_ore": 500_000})
        assert r.status_code == 422

    def test_nonpositive_amount_rejected(self, client):
        isk = _create_account(client, "ISK")
        r = client.put(f"/api/savings/accounts/{isk}/plan", json={"monthly_amount_ore": 0})
        assert r.status_code == 422

    def test_unknown_account_404(self, client):
        r = client.put("/api/savings/accounts/999/plan", json={"monthly_amount_ore": 500_000})
        assert r.status_code == 404

    def test_bad_start_date_rejected(self, client):
        isk = _create_account(client, "ISK")
        r = client.put(
            f"/api/savings/accounts/{isk}/plan",
            json={"monthly_amount_ore": 500_000, "start_date": "igår"},
        )
        assert r.status_code == 422

    def test_delete_ends_plan_and_404_without(self, client):
        isk = _create_account(client, "ISK")
        client.put(f"/api/savings/accounts/{isk}/plan", json={"monthly_amount_ore": 500_000})
        assert client.delete(f"/api/savings/accounts/{isk}/plan").status_code == 204
        assert client.delete(f"/api/savings/accounts/{isk}/plan").status_code == 404


class TestForecastSeries:
    def test_zero_rate_is_linear(self):
        series = _forecast_series(0, 500_000, 0.0)
        assert series[12] == 12 * 500_000

    def test_compounds_monthly(self):
        # 12 % årligen = 1 % per månad
        series = _forecast_series(10_000_000, 0, 12.0)
        assert series[1] == round(10_000_000 * 1.01)


class TestPlanSummary:
    def test_key_figures(self, db):
        a = _mk_account(db)
        _mk_snapshot(db, a.id, "2026-01-01", 10_000_000)
        upsert_plan(db, a.id, 500_000, "2026-01-01")
        _mk_snapshot(db, a.id, "2026-03-10", 11_800_000)
        s = plan_summary(db, [7.0], None, date(2026, 3, 15))
        acct = s["accounts"][0]
        # insättningar 1 jan, 1 feb, 1 mar = 3 st ovanpå startkapitalet
        assert acct["invested_ore"] == 10_000_000 + 3 * 500_000
        assert acct["current_value_ore"] == 11_800_000
        assert acct["return_ore"] == 300_000
        assert acct["return_pct"] == round(300_000 / 11_500_000, 4)
        assert s["total"]["monthly_amount_ore"] == 500_000

    def test_empty_without_active_plan(self, db):
        s = plan_summary(db, [7.0], None, date(2026, 3, 15))
        assert s == {"accounts": [], "total": None, "forecast": [], "milestones": []}

    def test_forecast_points_are_yearly(self, db):
        a = _mk_account(db)
        upsert_plan(db, a.id, 500_000, "2026-01-01")
        s = plan_summary(db, [0.0, 7.0], None, date(2026, 1, 1))
        assert [f["rate_pct"] for f in s["forecast"]] == [0.0, 7.0]
        zero = s["forecast"][0]["points"]
        # index 0 = dagens värde (inga snapshots → 0); efter 1 år: 12 insättningar
        assert zero[0] == {"year": 0, "value_ore": 0}
        assert zero[1]["value_ore"] == 12 * 500_000

    def test_milestones_with_zero_rate(self, db):
        a = _mk_account(db)
        _mk_snapshot(db, a.id, "2026-01-01", 9_000_000)
        upsert_plan(db, a.id, 500_000, "2026-01-01")
        s = plan_summary(db, [0.0], None, date(2026, 1, 1))
        amounts = [m["amount_ore"] for m in s["milestones"]]
        # tre närmaste över dagens värde 90 000 kr
        assert amounts == [10_000_000, 25_000_000, 50_000_000]
        first = s["milestones"][0]["reached"][0]
        # 90 000 → 100 000 kr: 2 månadsinsättningar à 5 000 kr
        assert first == {"rate_pct": 0.0, "date": "2026-03-01"}

    def test_custom_goal_included_and_flagged(self, db):
        a = _mk_account(db)
        upsert_plan(db, a.id, 500_000, "2026-01-01")
        s = plan_summary(db, [0.0], 120_000_000, date(2026, 1, 1))
        goal = next(m for m in s["milestones"] if m["is_goal"])
        assert goal["amount_ore"] == 120_000_000

    def test_unreachable_milestone_gives_null_date(self, db):
        a = _mk_account(db)
        upsert_plan(db, a.id, 100, "2026-01-01")  # 1 kr/mån når aldrig 100 000 kr
        s = plan_summary(db, [0.0], None, date(2026, 1, 1))
        assert s["milestones"][0]["reached"][0]["date"] is None


class TestPlanSummaryApi:
    def test_summary_via_api(self, client):
        isk = _create_account(client, "ISK")
        client.put(f"/api/savings/accounts/{isk}/plan", json={"monthly_amount_ore": 500_000})
        s = client.get("/api/savings/plan-summary").json()
        # planen startade idag: 1 insättning, inga snapshots
        assert s["accounts"][0]["invested_ore"] == 500_000
        assert s["total"]["current_value_ore"] == 0

    def test_rates_validation(self, client):
        isk = _create_account(client, "ISK")
        client.put(f"/api/savings/accounts/{isk}/plan", json={"monthly_amount_ore": 500_000})
        assert client.get("/api/savings/plan-summary?rates=abc").status_code == 422
        assert client.get("/api/savings/plan-summary?rates=4,7,10,12").status_code == 422
        assert client.get("/api/savings/plan-summary?rates=55").status_code == 422
        assert client.get("/api/savings/plan-summary?rates=4.5,7").status_code == 200

    def test_goal_validation(self, client):
        assert client.get("/api/savings/plan-summary?goal_ore=-5").status_code == 422
