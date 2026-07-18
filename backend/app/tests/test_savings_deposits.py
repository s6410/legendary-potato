"""Engångsinsättningar: insatt kapital-logik, plan-summary, history och API."""
from datetime import date

from sqlalchemy import select

from app.db.models import SavingsAccount, SavingsDeposit, SavingsPlan, SavingsSnapshot
from app.services.savings_plan import invested_at, plan_summary, upsert_plan


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


def _mk_deposit(db, account_id, deposit_date, amount_ore, note=None):
    db.add(
        SavingsDeposit(
            savings_account_id=account_id,
            deposit_date=deposit_date,
            amount_ore=amount_ore,
            note=note,
        )
    )
    db.flush()


def _plan_rows(db):
    return list(db.scalars(select(SavingsPlan)))


class TestInvestedWithDeposits:
    def test_deposit_counts_from_its_date(self, db):
        a = _mk_account(db)
        _mk_snapshot(db, a.id, "2026-06-30", 10_000_000)
        upsert_plan(db, a.id, 500_000, "2026-07-01")
        _mk_deposit(db, a.id, "2026-07-10", 200_000)
        rows = _plan_rows(db)
        assert invested_at(db, a.id, rows, date(2026, 7, 1)) == 10_000_000 + 500_000
        assert invested_at(db, a.id, rows, date(2026, 7, 10)) == 10_000_000 + 500_000 + 200_000

    def test_deposit_before_plan_start_moves_line_start(self, db):
        # snapshotvärdet 1 juni innehåller inte insättningen 15 juni —
        # insatt kapital ska öka med hela insättningen
        a = _mk_account(db)
        _mk_snapshot(db, a.id, "2026-06-01", 10_000_000)
        _mk_deposit(db, a.id, "2026-06-15", 1_000_000)
        upsert_plan(db, a.id, 500_000, "2026-07-01")
        rows = _plan_rows(db)
        assert invested_at(db, a.id, rows, date(2026, 6, 14)) is None
        assert invested_at(db, a.id, rows, date(2026, 6, 15)) == 11_000_000
        assert invested_at(db, a.id, rows, date(2026, 7, 1)) == 11_500_000

    def test_same_day_snapshot_not_double_counted(self, db):
        # värdet uppdaterat samma dag som insättningen (efter köpet) —
        # insättningen ingår redan i värdet och får inte räknas dubbelt
        a = _mk_account(db)
        _mk_deposit(db, a.id, "2026-04-08", 1_000_000)
        _mk_snapshot(db, a.id, "2026-04-08", 1_000_000)
        assert invested_at(db, a.id, [], date(2026, 4, 8)) == 1_000_000
        _mk_snapshot(db, a.id, "2026-06-30", 1_100_000)
        assert invested_at(db, a.id, [], date(2026, 6, 30)) == 1_000_000

    def test_backdated_deposit_without_early_values_assumes_zero_return(self, db):
        # första kända värdet efter insättningen: avkastning 0 fram till dess
        a = _mk_account(db)
        _mk_deposit(db, a.id, "2026-04-08", 1_000_000)
        _mk_snapshot(db, a.id, "2026-06-30", 1_050_000)
        assert invested_at(db, a.id, [], date(2026, 6, 30)) == 1_050_000
        assert invested_at(db, a.id, [], date(2026, 7, 15)) == 1_050_000

    def test_withdrawal_reduces_invested(self, db):
        a = _mk_account(db)
        _mk_deposit(db, a.id, "2026-07-01", 1_000_000)
        _mk_snapshot(db, a.id, "2026-07-01", 1_000_000)
        _mk_deposit(db, a.id, "2026-08-01", -200_000)
        assert invested_at(db, a.id, [], date(2026, 8, 1)) == 800_000

    def test_deposits_only_account_without_plan(self, db):
        a = _mk_account(db)
        _mk_deposit(db, a.id, "2026-07-01", 1_000_000)
        assert invested_at(db, a.id, [], date(2026, 6, 30)) is None
        assert invested_at(db, a.id, [], date(2026, 7, 1)) == 1_000_000

    def test_deposits_on_holdings_parent_account(self, db):
        # insättningar ligger på kontot; värden på innehaven
        isk = _mk_account(db)
        fond = _mk_account(db, "Fond", parent_id=isk.id, target_pct=100)
        _mk_deposit(db, isk.id, "2026-04-08", 1_000_000)
        _mk_snapshot(db, fond.id, "2026-04-08", 1_000_000)
        assert invested_at(db, isk.id, [], date(2026, 4, 8)) == 1_000_000


class TestUserScenario:
    """Kontoutdraget apr–jun 2026: klumpinsättningar + 5 000 kr/mån från 28 apr."""

    def _setup(self, db):
        isk = _mk_account(db)
        wef = _mk_account(db, "World Equity Fund", parent_id=isk.id, target_pct=82)
        plus = _mk_account(db, "PLUS Allabolag", parent_id=isk.id, target_pct=18)
        _mk_deposit(db, isk.id, "2026-04-08", 62_763_125)
        _mk_deposit(db, isk.id, "2026-04-09", 13_777_400)
        _mk_deposit(db, isk.id, "2026-05-15", 163_999_900)
        _mk_deposit(db, isk.id, "2026-05-15", 69_922_600)
        _mk_deposit(db, isk.id, "2026-05-18", 36_000_000)
        _mk_deposit(db, isk.id, "2026-05-18", 15_348_891)
        _mk_snapshot(db, wef.id, "2026-04-08", 62_763_125)
        _mk_snapshot(db, plus.id, "2026-04-09", 13_777_400)
        _mk_snapshot(db, wef.id, "2026-06-30", 318_361_982)
        _mk_snapshot(db, plus.id, "2026-06-30", 67_723_740)
        upsert_plan(db, isk.id, 500_000, "2026-04-28")
        return isk

    def test_invested_is_deposits_plus_monthly(self, db):
        isk = self._setup(db)
        rows = _plan_rows(db)
        oneoffs = 62_763_125 + 13_777_400 + 163_999_900 + 69_922_600 + 36_000_000 + 15_348_891
        # 3 månadsinsättningar: 28 apr, 28 maj, 28 jun
        assert invested_at(db, isk.id, rows, date(2026, 6, 30)) == oneoffs + 3 * 500_000

    def test_summary_shows_real_return(self, db):
        isk = self._setup(db)
        s = plan_summary(db, [7.0], None, date(2026, 6, 30))
        acct = next(x for x in s["accounts"] if x["id"] == isk.id)
        invested = 361_811_916 + 3 * 500_000
        assert acct["invested_ore"] == invested
        assert acct["current_value_ore"] == 386_085_722
        assert acct["return_ore"] == 386_085_722 - invested


def _create_account(client, name, **extra):
    r = client.post("/api/savings/accounts", json={"name": name, "asset_class": "equity", **extra})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _add_deposit(client, account_id, **body):
    return client.post(f"/api/savings/accounts/{account_id}/deposits", json=body)


class TestDepositApi:
    def test_create_list_delete_roundtrip(self, client):
        isk = _create_account(client, "ISK")
        r = _add_deposit(client, isk, deposit_date="2026-04-08", amount_ore=1_000_000, note="Arv")
        assert r.status_code == 201, r.text
        deposit_id = r.json()["id"]
        _add_deposit(client, isk, deposit_date="2026-05-15", amount_ore=2_000_000)
        deposits = client.get(f"/api/savings/accounts/{isk}/deposits").json()
        # senaste först
        assert [d["deposit_date"] for d in deposits] == ["2026-05-15", "2026-04-08"]
        assert deposits[1]["note"] == "Arv"
        assert client.delete(f"/api/savings/deposits/{deposit_id}").status_code == 204
        deposits = client.get(f"/api/savings/accounts/{isk}/deposits").json()
        assert len(deposits) == 1

    def test_deposit_on_holding_rejected(self, client):
        isk = _create_account(client, "ISK")
        fond = _create_account(client, "Fond", parent_id=isk, target_pct=100)
        r = _add_deposit(client, fond, deposit_date="2026-04-08", amount_ore=1_000_000)
        assert r.status_code == 422

    def test_zero_amount_rejected(self, client):
        isk = _create_account(client, "ISK")
        r = _add_deposit(client, isk, deposit_date="2026-04-08", amount_ore=0)
        assert r.status_code == 422

    def test_bad_date_rejected(self, client):
        isk = _create_account(client, "ISK")
        r = _add_deposit(client, isk, deposit_date="igår", amount_ore=1_000_000)
        assert r.status_code == 422

    def test_unknown_account_404(self, client):
        r = _add_deposit(client, 999, deposit_date="2026-04-08", amount_ore=1_000_000)
        assert r.status_code == 404

    def test_delete_unknown_404(self, client):
        assert client.delete("/api/savings/deposits/999").status_code == 404

    def test_deleting_account_deletes_deposits(self, client, db):
        isk = _create_account(client, "ISK")
        _add_deposit(client, isk, deposit_date="2026-04-08", amount_ore=1_000_000)
        client.delete(f"/api/savings/accounts/{isk}")
        assert list(db.scalars(select(SavingsDeposit))) == []


class TestHistoryInvested:
    def test_invested_series_includes_deposits_only_account(self, client):
        isk = _create_account(client, "ISK")
        client.post("/api/savings/snapshots", json={
            "snapshot_date": "2026-06-30",
            "values": [{"savings_account_id": isk, "value_ore": 1_000_000}],
        })
        client.post("/api/savings/snapshots", json={
            "snapshot_date": "2026-08-31",
            "values": [{"savings_account_id": isk, "value_ore": 2_150_000}],
        })
        _add_deposit(client, isk, deposit_date="2026-08-01", amount_ore=1_000_000)
        h = client.get("/api/savings/history").json()
        assert h["dates"] == ["2026-06-30", "2026-08-31"]
        # 30 jun: före första insättningen → null; 31 aug: värdet vid 30 jun
        # är baslinjen (inga planer) + insättningen
        assert h["invested"] == [None, 1_000_000 + 1_000_000]

    def test_invested_series_combines_plan_and_deposits(self, client):
        isk = _create_account(client, "ISK")
        client.post("/api/savings/snapshots", json={
            "snapshot_date": "2026-06-30",
            "values": [{"savings_account_id": isk, "value_ore": 1_000_000}],
        })
        client.put(
            f"/api/savings/accounts/{isk}/plan",
            json={"monthly_amount_ore": 500_000, "start_date": "2026-07-15"},
        )
        _add_deposit(client, isk, deposit_date="2026-08-01", amount_ore=1_000_000)
        client.post("/api/savings/snapshots", json={
            "snapshot_date": "2026-08-31",
            "values": [{"savings_account_id": isk, "value_ore": 3_100_000}],
        })
        h = client.get("/api/savings/history").json()
        # startkapital 1 000 000 + 2 månadsinsättningar (15 jul, 15 aug) + klump
        assert h["invested"] == [None, 1_000_000 + 2 * 500_000 + 1_000_000]
