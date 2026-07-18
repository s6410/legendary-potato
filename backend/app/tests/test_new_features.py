"""Tester för medlemsdimension, insikter, prognos, PDF, årsrapport, rebalansering."""
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


def _import_file(client, filename: str, account_name: str = "Konto") -> dict:
    data = (FIXTURES / filename).read_bytes()
    insp = client.post("/api/import/inspect", files={"file": (filename, data)}).json()["inspection"]
    acct = client.post("/api/accounts", json={"name": account_name}).json()["id"]
    pid = client.post("/api/import/profiles", json={
        "fingerprint": insp["fingerprint"], "name": filename, "file_type": insp["file_type"],
        "column_mapping": insp["suggested_mapping"], "default_account_id": acct,
        "delimiter": insp["delimiter"], "encoding": insp["encoding"],
        "decimal_separator": insp["suggested_decimal_separator"],
        "thousands_separator": insp["suggested_thousands_separator"],
        "date_format": insp["suggested_date_format"],
        "header_row_index": insp["header_row_index"],
        "invert_sign": insp["suggested_invert_sign"],
    }).json()["id"]
    commit = client.post("/api/import/commit", files={"file": (filename, data)},
                         data={"profile_id": str(pid)}).json()
    return {"account_id": acct, "profile_id": pid, **commit}


class TestMember:
    def test_handelsbanken_member_column_detected_and_imported(self, client):
        data = (FIXTURES / "handelsbanken_kort.csv").read_bytes()
        insp = client.post(
            "/api/import/inspect", files={"file": ("handelsbanken_kort.csv", data)}
        ).json()["inspection"]
        assert insp["suggested_mapping"]["member"] == 1  # Ägare-kolumnen

        result = _import_file(client, "handelsbanken_kort.csv", "HB Kort")
        assert result["inserted"] == 4

        rows = client.get("/api/transactions", params={"member": "ANNA"}).json()["rows"]
        assert len(rows) == 2
        assert all(r["member"] == "ANNA" for r in rows)

    def test_manual_member_and_bulk(self, client):
        _import_file(client, "swedbank.csv")
        rows = client.get("/api/transactions").json()["rows"]
        ids = [r["id"] for r in rows[:2]]
        r = client.post("/api/transactions/bulk-member", json={"ids": ids, "member": "Erik"}).json()
        assert r["updated"] == 2
        assert "Erik" in client.get("/api/transactions/members").json()

    def test_by_member_settlement(self, client):
        _import_file(client, "handelsbanken_kort.csv", "HB Kort")
        r = client.get("/api/insights/by-member", params={"period": "2026-06"}).json()
        members = {m["member"]: m for m in r["members"]}
        # köpen är teckeninverterade (kreditkort): utgifter negativa
        assert members["ANNA"]["expenses_ore"] == -(124900 + 29800)
        assert members["ERIK"]["expenses_ore"] == -83250
        settlement = {s["member"]: s for s in r["settlement"]}
        total = 124900 + 29800 + 83250
        assert settlement["ANNA"]["diff_ore"] == round(124900 + 29800 - total / 2)


class TestObservations:
    def test_category_spike_and_uncategorized(self, client, db):
        from app.db.models import Account, ImportBatch, ImportFormatProfile, Transaction
        from app.services.normalize import normalize_description

        a = Account(name="A")
        db.add(a)
        db.flush()
        p = ImportFormatProfile(fingerprint="z", name="P", file_type="csv", column_mapping="{}")
        db.add(p)
        db.flush()
        b = ImportBatch(account_id=a.id, profile_id=p.id)
        db.add(b)
        db.flush()
        from sqlalchemy import select

        from app.db.models import Category

        el = next(c.id for c in db.scalars(select(Category)) if c.name == "El")
        # maj: 800 kr el, juni: 2000 kr el (+150 %) + 6 okategoriserade
        for i, (d, amt, cat) in enumerate(
            [("2026-05-28", -80000, el), ("2026-06-27", -200000, el)]
            + [(f"2026-06-{10 + k:02d}", -5000, None) for k in range(6)]
        ):
            db.add(Transaction(
                account_id=a.id, batch_id=b.id, booked_date=d, amount_ore=amt,
                description_raw=f"T{i}", description_norm=normalize_description(f"T{i}"),
                category_id=cat, dedup_hash=f"o{i}", occurrence_index=0,
            ))
        db.commit()

        obs = client.get("/api/insights/observations", params={"month": "2026-06"}).json()
        types = {o["type"] for o in obs}
        assert "category_spike" in types
        assert "uncategorized" in types
        spike = next(o for o in obs if o["type"] == "category_spike")
        assert "Boende" in spike["title"] and "150" in spike["title"]

    def test_price_hike_detected(self, client, db):
        from app.db.models import Account, ImportBatch, ImportFormatProfile, Transaction

        a = Account(name="A")
        db.add(a)
        db.flush()
        p = ImportFormatProfile(fingerprint="w", name="P", file_type="csv", column_mapping="{}")
        db.add(p)
        db.flush()
        b = ImportBatch(account_id=a.id, profile_id=p.id)
        db.add(b)
        db.flush()
        amounts = [16900] * 5 + [19900]  # höjning sista månaden
        for month, amt in enumerate(amounts, start=1):
            db.add(Transaction(
                account_id=a.id, batch_id=b.id, booked_date=f"2026-{month:02d}-14",
                amount_ore=-amt, description_raw="SPOTIFY AB", description_norm="spotify ab",
                dedup_hash=f"p{month}", occurrence_index=0,
            ))
        db.commit()
        obs = client.get("/api/insights/observations", params={"month": "2026-06"}).json()
        assert any(o["type"] == "price_hike" and "SPOTIFY" in o["title"] for o in obs)


class TestCashflowForecast:
    def test_events_and_buffer(self, client, db):
        from app.db.models import Account, ImportBatch, ImportFormatProfile, Transaction

        a = Account(name="A")
        db.add(a)
        db.flush()
        p = ImportFormatProfile(fingerprint="v", name="P", file_type="csv", column_mapping="{}")
        db.add(p)
        db.flush()
        b = ImportBatch(account_id=a.id, profile_id=p.id)
        db.add(b)
        db.flush()
        i = 0
        for month in range(1, 7):
            for d, amt, desc in [
                (25, 4000000, "Lön Arbetsgivaren"),
                (14, -16900, "SPOTIFY AB"),
                (27, -1150000, "Hyra Bostads AB"),
            ]:
                i += 1
                db.add(Transaction(
                    account_id=a.id, batch_id=b.id, booked_date=f"2026-{month:02d}-{d:02d}",
                    amount_ore=amt, description_raw=desc, description_norm=desc.casefold(),
                    dedup_hash=f"c{i}", occurrence_index=0,
                ))
        db.commit()
        # sparande för bufferttid
        sid = client.post("/api/savings/accounts", json={"name": "Buffert", "asset_class": "cash"}).json()["id"]
        client.post("/api/savings/snapshots", json={
            "snapshot_date": "2026-06-30",
            "values": [{"savings_account_id": sid, "value_ore": 20000000}],
        })

        fc = client.get("/api/insights/cashflow-forecast", params={"days": 60}).json()
        kinds = {e["kind"] for e in fc["events"]}
        assert "income" in kinds and "expense" in kinds
        assert any("Lön" in e["description"] for e in fc["events"])
        assert len(fc["daily"]) == 60
        assert fc["buffer_months"] is not None and fc["buffer_months"] > 0


class TestPdfImport:
    def test_entercard_pdf_full_flow(self, client):
        result = _import_file(client, "entercard_faktura.pdf", "Entercard")
        assert result["inserted"] == 4
        rows = client.get("/api/transactions", params={"account_id": result["account_id"]}).json()["rows"]
        amounts = sorted(r["amount_ore"] for r in rows)
        # köp negativa efter invertering, inbetalning positiv
        assert amounts == [-389000, -124900, -16900, 845000]

    def test_pdf_without_transactions_rejected(self, client):
        r = client.post("/api/import/inspect", files={"file": ("tom.pdf", b"%PDF-1.4\n%%EOF")})
        assert r.status_code == 422


class TestYearlyReport:
    def test_yearly_composition(self, client, db):
        from app.db.models import Account, ImportBatch, ImportFormatProfile, Transaction

        a = Account(name="A")
        db.add(a)
        db.flush()
        p = ImportFormatProfile(fingerprint="u", name="P", file_type="csv", column_mapping="{}")
        db.add(p)
        db.flush()
        b = ImportBatch(account_id=a.id, profile_id=p.id)
        db.add(b)
        db.flush()
        i = 0
        for year, monthly_food in ((2025, -300000), (2026, -450000)):
            for month in range(1, 13 if year == 2025 else 7):
                i += 1
                db.add(Transaction(
                    account_id=a.id, batch_id=b.id, booked_date=f"{year}-{month:02d}-10",
                    amount_ore=monthly_food, description_raw="ICA", description_norm="ica",
                    dedup_hash=f"y{i}", occurrence_index=0,
                ))
        db.commit()

        report = client.get("/api/reports/yearly", params={"year": 2026}).json()
        assert report["year"] == 2026
        assert len(report["months"]) == 12
        assert report["summary"]["expenses_ore"] == -450000 * 6
        assert report["top_merchants"][0]["description_norm"] == "ica"


class TestRebalance:
    def _setup(self, client):
        isk = client.post("/api/savings/accounts", json={"name": "ISK", "asset_class": "equity"}).json()["id"]
        rf = client.post("/api/savings/accounts", json={"name": "RF", "asset_class": "fixed_income"}).json()["id"]
        kf = client.post("/api/savings/accounts", json={"name": "KF", "asset_class": "cash"}).json()["id"]
        client.post("/api/savings/snapshots", json={
            "snapshot_date": "2026-06-30",
            "values": [
                {"savings_account_id": isk, "value_ore": 70000000},
                {"savings_account_id": rf, "value_ore": 15000000},
                {"savings_account_id": kf, "value_ore": 15000000},
            ],
        })

    def test_contribution_fills_underweight(self, client):
        # mål 60/20/20, läge 70/15/15 → nysparande ska gå till räntor+kontanter
        self._setup(client)
        plan = client.get("/api/savings/rebalance", params={"contribution_ore": 1000000}).json()
        assert plan["requires_selling"] is False
        classes = {a["asset_class"] for a in plan["allocations"]}
        assert "equity" not in classes
        assert sum(a["amount_ore"] for a in plan["allocations"]) == 1000000

    def test_zero_contribution_suggests_moves(self, client):
        self._setup(client)
        plan = client.get("/api/savings/rebalance").json()
        assert plan["requires_selling"] is True
        moves = {a["asset_class"]: a["amount_ore"] for a in plan["allocations"]}
        assert moves["equity"] == -10000000   # sälj 100 000 kr aktier
        assert moves["fixed_income"] == 5000000
        assert moves["cash"] == 5000000
