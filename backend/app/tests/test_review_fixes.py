"""Regressionstester för fynd från kodgranskningen."""
import pytest

from app.services.parsing import ParseOptions, parse_amount, parse_with_options


@pytest.mark.parametrize(
    "raw,dec,expected",
    [
        ("1 234,00-", ",", -123400),   # avslutande minus
        ("(1 234,00)", ",", -123400),  # parentesnegativ
        ("500-", ",", -50000),
    ],
)
def test_parse_amount_negative_formats(raw, dec, expected):
    assert parse_amount(raw, dec, " ") == expected


def test_split_columns_skip_rows_without_amount():
    data = "\n".join(
        [
            "Datum;Text;Insättning;Uttag;Saldo",
            "2026-06-01;Ingående saldo;;;10 000,00",
            "2026-06-02;Lön;1 000,00;;11 000,00",
            "2026-06-03;Hyra;;500,00;10 500,00",
        ]
    ).encode("utf-8")
    opts = ParseOptions(
        file_type="csv",
        column_mapping={"date": 0, "description": 1, "amount": None,
                        "amount_in": 2, "amount_out": 3, "balance": 4},
        delimiter=";", thousands_separator=" ",
    )
    res = parse_with_options(data, "split.csv", opts)
    assert [r.amount_ore for r in res.rows] == [100000, -50000]
    assert len(res.skipped) == 1
    assert res.skipped[0]["reason"] == "tomt belopp"


def test_utf16_files_are_decoded():
    from app.services.parsing import read_raw_rows

    data = "Datum;Text;Belopp\n2026-06-01;Kaffe;-45,00".encode("utf-16")
    _, rows, encoding, delimiter = read_raw_rows(data, "utf16.csv")
    assert encoding == "utf-16"
    assert rows[1][1] == "Kaffe"


def _find_category(client, name):
    for root in client.get("/api/categories").json():
        if root["name"] == name:
            return root["id"]
        for child in root["children"]:
            if child["name"] == name:
                return child["id"]
    raise AssertionError(name)


def _import_swedbank(client):
    from pathlib import Path

    data = (Path(__file__).parent / "fixtures" / "swedbank.csv").read_bytes()
    insp = client.post("/api/import/inspect", files={"file": ("swedbank.csv", data)}).json()["inspection"]
    acct = client.post("/api/accounts", json={"name": "K"}).json()["id"]
    pid = client.post("/api/import/profiles", json={
        "fingerprint": insp["fingerprint"], "name": "S", "file_type": "csv",
        "column_mapping": insp["suggested_mapping"], "default_account_id": acct,
        "delimiter": insp["delimiter"], "encoding": insp["encoding"],
        "decimal_separator": insp["suggested_decimal_separator"],
        "date_format": insp["suggested_date_format"],
        "header_row_index": insp["header_row_index"],
    }).json()["id"]
    client.post("/api/import/commit", files={"file": ("swedbank.csv", data)},
                data={"profile_id": str(pid)})
    return acct


def test_rule_pattern_change_releases_nonmatching_transactions(client):
    _import_swedbank(client)
    livsmedel = _find_category(client, "Livsmedel")

    rule = client.post("/api/rules", json={
        "match_type": "contains", "pattern": "ica", "category_id": livsmedel,
    }).json()
    assert rule["affected"] == 1

    # byt mönster till något som INTE matchar ICA-transaktionen
    client.patch(f"/api/rules/{rule['id']}", json={"pattern": "willys"})
    txn = client.get("/api/transactions", params={"q": "ica"}).json()["rows"][0]
    assert txn["category_id"] is None  # släppt, inte kvarstämplad


def test_manual_link_after_dismissed_suggestion_reuses_row(client, db):
    from app.db.models import Account, ImportBatch, ImportFormatProfile, Transaction

    a = Account(name="A")
    db.add(a)
    db.flush()
    p = ImportFormatProfile(fingerprint="x", name="P", file_type="csv", column_mapping="{}")
    db.add(p)
    db.flush()
    b = ImportBatch(account_id=a.id, profile_id=p.id)
    db.add(b)
    db.flush()
    t1 = Transaction(account_id=a.id, batch_id=b.id, booked_date="2026-06-01",
                     amount_ore=-129900, description_raw="ELGIGANTEN",
                     description_norm="elgiganten", dedup_hash="h1", occurrence_index=0)
    t2 = Transaction(account_id=a.id, batch_id=b.id, booked_date="2026-06-10",
                     amount_ore=129900, description_raw="ELGIGANTEN",
                     description_norm="elgiganten", dedup_hash="h2", occurrence_index=0)
    db.add_all([t1, t2])
    db.commit()

    client.post("/api/links/scan")
    [sug] = client.get("/api/links/suggestions").json()
    client.post(f"/api/links/{sug['id']}/dismiss")

    # manuell länkning av samma par ska INTE ge 500 (UNIQUE-krock) utan återanvända raden
    r = client.post("/api/links", json={"txn_a_id": t1.id, "txn_b_id": t2.id, "kind": "refund"})
    assert r.status_code == 201
    assert r.json()["id"] == sug["id"]


def test_recurring_excludes_transfer_categories(client, db):
    from app.db.models import Account, Category, ImportBatch, ImportFormatProfile, Transaction
    from sqlalchemy import select

    a = Account(name="A")
    db.add(a)
    db.flush()
    p = ImportFormatProfile(fingerprint="y", name="P", file_type="csv", column_mapping="{}")
    db.add(p)
    db.flush()
    b = ImportBatch(account_id=a.id, profile_id=p.id)
    db.add(b)
    db.flush()
    sparande = next(
        c.id for c in db.scalars(select(Category)) if c.name == "Månadssparande"
    )
    for month in range(1, 7):
        db.add(Transaction(
            account_id=a.id, batch_id=b.id, booked_date=f"2026-{month:02d}-25",
            amount_ore=-500000, description_raw="Överföring till sparkonto",
            description_norm="till sparkonto", category_id=sparande,
            dedup_hash=f"s{month}", occurrence_index=0,
        ))
    db.commit()

    series = client.get("/api/insights/recurring").json()
    assert series == []  # överföringar är inte återkommande UTGIFTER


def test_revert_decrements_rule_hit_count(client):
    from pathlib import Path

    _import_swedbank(client)
    livsmedel = _find_category(client, "Livsmedel")
    client.post("/api/rules", json={"match_type": "contains", "pattern": "willys", "category_id": livsmedel})

    data = (Path(__file__).parent / "fixtures" / "nordea.csv").read_bytes()
    insp = client.post("/api/import/inspect", files={"file": ("nordea.csv", data)}).json()["inspection"]
    acct2 = client.post("/api/accounts", json={"name": "K2"}).json()["id"]
    pid = client.post("/api/import/profiles", json={
        "fingerprint": insp["fingerprint"], "name": "N", "file_type": "csv",
        "column_mapping": insp["suggested_mapping"], "default_account_id": acct2,
        "delimiter": insp["delimiter"], "encoding": insp["encoding"],
        "decimal_separator": insp["suggested_decimal_separator"],
        "date_format": insp["suggested_date_format"],
        "header_row_index": insp["header_row_index"],
    }).json()["id"]
    commit = client.post("/api/import/commit", files={"file": ("nordea.csv", data)},
                         data={"profile_id": str(pid)}).json()

    [rule] = client.get("/api/rules").json()
    assert rule["hit_count"] == 1  # Willys-raden i nordea.csv

    client.post(f"/api/import/batches/{commit['batch_id']}/revert")
    [rule] = client.get("/api/rules").json()
    assert rule["hit_count"] == 0
