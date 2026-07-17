"""Fas 5: kvittning, prenumerationer, insikter, budget, sparande."""
from app.db.models import Account, ImportBatch, ImportFormatProfile, Transaction
from app.services import links as links_service
from app.services import recurring as recurring_service
from app.services.normalize import normalize_description


def _seed_txn(db, account_id, batch_id, date, amount, desc, category_id=None, i=[0]):
    i[0] += 1
    txn = Transaction(
        account_id=account_id,
        batch_id=batch_id,
        booked_date=date,
        amount_ore=amount,
        description_raw=desc,
        description_norm=normalize_description(desc),
        category_id=category_id,
        dedup_hash=f"seed-{i[0]}",
        occurrence_index=0,
    )
    db.add(txn)
    db.flush()
    return txn


def _setup(db, n_accounts=1):
    accounts = []
    for k in range(n_accounts):
        a = Account(name=f"Konto {k}")
        db.add(a)
        db.flush()
        p = ImportFormatProfile(
            fingerprint=f"fp-{k}", name="P", file_type="csv", column_mapping="{}"
        )
        db.add(p)
        db.flush()
        b = ImportBatch(account_id=a.id, profile_id=p.id)
        db.add(b)
        db.flush()
        accounts.append((a.id, b.id))
    return accounts


class TestRefundMatching:
    def test_real_refund_suggested(self, db):
        [(acct, batch)] = _setup(db)
        _seed_txn(db, acct, batch, "2026-06-01", -129900, "ELGIGANTEN STOCKHOLM")
        _seed_txn(db, acct, batch, "2026-06-20", 129900, "ELGIGANTEN STOCKHOLM")
        created = links_service.suggest_refunds(db)
        assert created == 1

    def test_small_coincidence_rejected(self, db):
        # två olika handlare, litet belopp, långt isär → ingen träff
        [(acct, batch)] = _setup(db)
        _seed_txn(db, acct, batch, "2026-05-01", -4500, "PRESSBYRAN CITY")
        _seed_txn(db, acct, batch, "2026-06-12", 4500, "SWISH ANNA ANDERSSON")
        assert links_service.suggest_refunds(db) == 0

    def test_dismissed_pair_not_resuggested(self, db, client):
        [(acct, batch)] = _setup(db)
        _seed_txn(db, acct, batch, "2026-06-01", -129900, "ELGIGANTEN STOCKHOLM")
        _seed_txn(db, acct, batch, "2026-06-20", 129900, "ELGIGANTEN STOCKHOLM")
        links_service.suggest_refunds(db)
        db.commit()
        [sug] = client.get("/api/links/suggestions").json()
        client.post(f"/api/links/{sug['id']}/dismiss")
        session = client.app.state.session_factory()
        try:
            assert links_service.suggest_refunds(session) == 0
        finally:
            session.close()

    def test_transfer_between_accounts(self, db):
        [(a1, b1), (a2, b2)] = _setup(db, 2)
        _seed_txn(db, a1, b1, "2026-06-05", -500000, "Överföring till sparkonto")
        _seed_txn(db, a2, b2, "2026-06-05", 500000, "Överföring från lönekonto")
        created = links_service.suggest_refunds(db)
        assert created == 1


class TestRecurring:
    def test_monthly_subscription_detected(self, db):
        [(acct, batch)] = _setup(db)
        for month in range(1, 7):
            _seed_txn(db, acct, batch, f"2026-{month:02d}-14", -16900, "SPOTIFY AB")
        series = recurring_service.detect_recurring(db, reference_date="2026-06-20")
        assert len(series) == 1
        s = series[0]
        assert s["cadence"] == "monthly"
        assert s["median_amount_ore"] == 16900
        assert s["annual_cost_ore"] == 16900 * 12
        assert s["next_expected_date"].startswith("2026-07")
        assert not s["possibly_ended"]

    def test_irregular_payee_not_detected(self, db):
        [(acct, batch)] = _setup(db)
        for d, amt in [("2026-01-03", -25000), ("2026-01-19", -103000),
                       ("2026-03-28", -7000), ("2026-06-11", -56000)]:
            _seed_txn(db, acct, batch, d, amt, "RESTAURANG PELIKAN")
        assert recurring_service.detect_recurring(db, reference_date="2026-06-20") == []

    def test_ended_subscription_flagged(self, db):
        [(acct, batch)] = _setup(db)
        for month in range(1, 5):
            _seed_txn(db, acct, batch, f"2026-{month:02d}-05", -9900, "NETFLIX.COM")
        series = recurring_service.detect_recurring(db, reference_date="2026-06-25")
        assert series[0]["possibly_ended"] is True


class TestInsights:
    def test_confirmed_refund_nets_out_of_stats(self, db, client):
        [(acct, batch)] = _setup(db)
        _seed_txn(db, acct, batch, "2026-06-02", -300000, "BAUHAUS SICKLA")
        _seed_txn(db, acct, batch, "2026-06-10", 300000, "BAUHAUS SICKLA")
        _seed_txn(db, acct, batch, "2026-06-15", -50000, "WILLYS")
        links_service.suggest_refunds(db)
        db.commit()

        before = client.get("/api/insights/summary", params={"period": "2026-06"}).json()
        assert before["current"]["expenses_ore"] == -350000  # förslag påverkar inte

        [sug] = client.get("/api/links/suggestions").json()
        client.post(f"/api/links/{sug['id']}/confirm")
        after = client.get("/api/insights/summary", params={"period": "2026-06"}).json()
        assert after["current"]["expenses_ore"] == -50000
        assert after["current"]["income_ore"] == 0

        included = client.get(
            "/api/insights/summary", params={"period": "2026-06", "include_refunds": "true"}
        ).json()
        assert included["current"]["expenses_ore"] == -350000

    def test_by_category_rollup_and_drilldown(self, db, client):
        from sqlalchemy import select

        from app.db.models import Category

        [(acct, batch)] = _setup(db)
        cats = {c.name: c.id for c in db.scalars(select(Category))}
        _seed_txn(db, acct, batch, "2026-06-01", -10000, "ICA", cats["Livsmedel"])
        _seed_txn(db, acct, batch, "2026-06-02", -20000, "COOP", cats["Livsmedel"])
        _seed_txn(db, acct, batch, "2026-06-03", -5000, "ESPRESSO HOUSE", cats["Café"])
        _seed_txn(db, acct, batch, "2026-06-04", -7000, "OKÄND")
        db.commit()

        roots = client.get("/api/insights/by-category", params={"period": "2026-06"}).json()
        mat = next(r for r in roots if r["name"] == "Mat")
        assert mat["amount_ore"] == -35000
        okat = next(r for r in roots if r["name"] == "Okategoriserat")
        assert okat["amount_ore"] == -7000

        mat_id = next(c.id for c in db.scalars(select(Category)) if c.name == "Mat" and c.parent_id is None)
        subs = client.get(
            "/api/insights/by-category", params={"period": "2026-06", "parent_id": mat_id}
        ).json()
        livsmedel = next(s for s in subs if s["name"] == "Livsmedel")
        assert livsmedel["amount_ore"] == -30000

    def test_budget_status(self, db, client):
        from sqlalchemy import select

        from app.db.models import Category

        [(acct, batch)] = _setup(db)
        cats = {c.name: c.id for c in db.scalars(select(Category))}
        _seed_txn(db, acct, batch, "2026-06-05", -40000, "ICA", cats["Livsmedel"])
        db.commit()
        client.post("/api/budgets", json={
            "category_id": cats["Livsmedel"], "amount_ore": 100000, "valid_from": "2026-01",
        })
        items = client.get("/api/budgets", params={"month": "2026-06"}).json()["items"]
        assert len(items) == 1
        assert items[0]["spent_ore"] == 40000
        assert items[0]["remaining_ore"] == 60000
        assert items[0]["progress"] == 0.4


class TestSavings:
    def test_snapshots_and_drift(self, client):
        isk = client.post("/api/savings/accounts", json={"name": "ISK", "asset_class": "equity"}).json()["id"]
        ranta = client.post("/api/savings/accounts", json={"name": "Räntefond", "asset_class": "fixed_income"}).json()["id"]
        buffert = client.post("/api/savings/accounts", json={"name": "Buffert", "asset_class": "cash"}).json()["id"]

        client.post("/api/savings/snapshots", json={
            "snapshot_date": "2026-06-30",
            "values": [
                {"savings_account_id": isk, "value_ore": 70000000},     # 700 000 kr
                {"savings_account_id": ranta, "value_ore": 15000000},   # 150 000 kr
                {"savings_account_id": buffert, "value_ore": 15000000}, # 150 000 kr
            ],
        })
        drift = client.get("/api/savings/drift").json()
        assert drift["total_ore"] == 100000000
        eq = next(c for c in drift["classes"] if c["asset_class"] == "equity")
        assert eq["current_pct"] == 70.0
        assert eq["target_pct"] == 60.0     # seedad målfördelning
        assert eq["drift_pct"] == 10.0
        assert eq["drift_ore"] == 10000000  # 100 000 kr över målet

        history = client.get("/api/savings/history").json()
        assert history["dates"] == ["2026-06-30"]
        assert len(history["series"]) == 3

    def test_targets_must_sum_to_100(self, client):
        r = client.put("/api/savings/targets", json={"targets": [
            {"asset_class": "equity", "target_pct": 80},
            {"asset_class": "cash", "target_pct": 10},
        ]})
        assert r.status_code == 422
