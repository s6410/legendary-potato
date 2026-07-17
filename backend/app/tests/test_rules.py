"""Regelmotorns precedens, lärande och rättelser."""
from pathlib import Path

from app.db.models import CategorizationRule
from app.services.rules import load_rules, match_rule

FIXTURES = Path(__file__).parent / "fixtures"


def _rule(**kw) -> CategorizationRule:
    defaults = dict(match_type="exact", pattern="", category_id=1, account_id=None,
                    priority=0, updated_at="2026-01-01")
    defaults.update(kw)
    return CategorizationRule(**defaults)


class TestPrecedence:
    def test_exact_beats_prefix_and_contains(self):
        rules = [
            _rule(id=1, match_type="contains", pattern="ica", category_id=10),
            _rule(id=2, match_type="prefix", pattern="ica supermarket", category_id=20),
            _rule(id=3, match_type="exact", pattern="ica supermarket söder", category_id=30),
        ]
        rules = sorted(rules, key=lambda r: r.id)  # oordnat in, load_rules sorterar normalt
        from app.services.rules import _TYPE_ORDER  # noqa: F401
        ordered = sorted(rules, key=lambda r: ({"exact": 0, "prefix": 1, "contains": 2}[r.match_type], -len(r.pattern)))
        m = match_rule(ordered, "ica supermarket söder")
        assert m.category_id == 30

    def test_longest_prefix_wins(self):
        ordered = [
            _rule(id=1, match_type="prefix", pattern="ica supermarket", category_id=20),
            _rule(id=2, match_type="prefix", pattern="ica", category_id=10),
        ]
        assert match_rule(ordered, "ica supermarket söder").category_id == 20

    def test_account_specific_beats_global(self, db):
        from app.db.models import Account

        db.add(Account(id=1, name="Konto A"))
        db.flush()
        db.add(_rule(match_type="exact", pattern="spotify ab", category_id=1, account_id=None))
        db.add(_rule(match_type="exact", pattern="spotify ab", category_id=2, account_id=1))
        db.flush()
        rules = load_rules(db)
        m = match_rule(rules, "spotify ab", account_id=1)
        assert m.category_id == 2
        m_other = match_rule(rules, "spotify ab", account_id=99)
        assert m_other.category_id == 1


def _setup_transactions(client) -> tuple[int, int]:
    acct = client.post("/api/accounts", json={"name": "Konto"}).json()["id"]
    data = (FIXTURES / "swedbank.csv").read_bytes()
    insp = client.post("/api/import/inspect", files={"file": ("swedbank.csv", data)}).json()["inspection"]
    pid = client.post("/api/import/profiles", json={
        "fingerprint": insp["fingerprint"], "name": "Swedbank", "file_type": insp["file_type"],
        "column_mapping": insp["suggested_mapping"], "default_account_id": acct,
        "delimiter": insp["delimiter"], "encoding": insp["encoding"],
        "decimal_separator": insp["suggested_decimal_separator"],
        "date_format": insp["suggested_date_format"],
        "header_row_index": insp["header_row_index"],
    }).json()["id"]
    client.post("/api/import/commit", files={"file": ("swedbank.csv", data)},
                data={"profile_id": str(pid)})
    return acct, pid


def _find_category(client, name: str) -> int:
    tree = client.get("/api/categories").json()
    for root in tree:
        if root["name"] == name:
            return root["id"]
        for child in root["children"]:
            if child["name"] == name:
                return child["id"]
    raise AssertionError(f"kategori {name} saknas")


def test_learning_flow_bulk_categorize_creates_rule_and_applies(client):
    _setup_transactions(client)
    livsmedel = _find_category(client, "Livsmedel")
    txns = client.get("/api/transactions", params={"q": "ica"}).json()["rows"]
    assert len(txns) == 1

    r = client.post("/api/transactions/bulk-categorize", json={
        "ids": [txns[0]["id"]],
        "category_id": livsmedel,
        "rule": {"match_type": "prefix", "pattern": "ica supermarket"},
    }).json()
    assert r["categorized"] == 1
    assert r["rule_id"] is not None

    # regeln appliceras på framtida importer: importera nordeafilen med ICA? nej —
    # verifiera i stället att regeln matchar vid nästa apply-all och import-preview
    rules = client.get("/api/rules").json()
    assert any(rule["pattern"] == "ica supermarket" for rule in rules)


def test_manual_categorization_shielded_from_rules(client):
    _setup_transactions(client)
    livsmedel = _find_category(client, "Livsmedel")
    cafe = _find_category(client, "Café")
    txns = client.get("/api/transactions", params={"q": "ica"}).json()["rows"]
    txn_id = txns[0]["id"]

    # manuell kategorisering
    client.patch(f"/api/transactions/{txn_id}", json={"category_id": cafe})
    # regel som annars skulle träffa
    client.post("/api/rules", json={"match_type": "contains", "pattern": "ica", "category_id": livsmedel})
    client.post("/api/rules/apply-all")

    after = client.get("/api/transactions", params={"q": "ica"}).json()["rows"][0]
    assert after["category_id"] == cafe
    assert after["category_source"] == "manual"


def test_rule_correction_propagates_to_rule_sourced_only(client):
    _setup_transactions(client)
    livsmedel = _find_category(client, "Livsmedel")
    restaurang = _find_category(client, "Restaurang")

    rule = client.post("/api/rules", json={
        "match_type": "contains", "pattern": "ica", "category_id": livsmedel,
    }).json()
    assert rule["affected"] == 1

    r = client.patch(f"/api/rules/{rule['id']}", json={"category_id": restaurang}).json()
    assert r["affected"] >= 1
    after = client.get("/api/transactions", params={"q": "ica"}).json()["rows"][0]
    assert after["category_id"] == restaurang
    assert after["category_source"] == "rule"


def test_rules_apply_on_import(client):
    acct = client.post("/api/accounts", json={"name": "Konto"}).json()["id"]
    livsmedel = _find_category(client, "Livsmedel")
    client.post("/api/rules", json={"match_type": "contains", "pattern": "willys", "category_id": livsmedel})

    data = (FIXTURES / "nordea.csv").read_bytes()
    insp = client.post("/api/import/inspect", files={"file": ("nordea.csv", data)}).json()["inspection"]
    pid = client.post("/api/import/profiles", json={
        "fingerprint": insp["fingerprint"], "name": "Nordea", "file_type": "csv",
        "column_mapping": insp["suggested_mapping"], "default_account_id": acct,
        "delimiter": insp["delimiter"], "encoding": insp["encoding"],
        "decimal_separator": insp["suggested_decimal_separator"],
        "date_format": insp["suggested_date_format"],
        "header_row_index": insp["header_row_index"],
    }).json()["id"]
    preview = client.post("/api/import/preview", files={"file": ("nordea.csv", data)},
                          data={"profile_id": str(pid)}).json()
    assert preview["auto_categorized"] == 1
    willys_row = next(r for r in preview["rows"] if "Willys" in r["description"])
    assert willys_row["category_id"] == livsmedel


def test_category_delete_with_reassign(client):
    _setup_transactions(client)
    livsmedel = _find_category(client, "Livsmedel")
    ovrigt = _find_category(client, "Övrigt")
    txns = client.get("/api/transactions", params={"q": "ica"}).json()["rows"]
    client.patch(f"/api/transactions/{txns[0]['id']}", json={"category_id": livsmedel})

    r = client.delete(f"/api/categories/{livsmedel}")
    assert r.status_code == 409  # används → kräver reassign

    r = client.delete(f"/api/categories/{livsmedel}", params={"reassign_to": ovrigt})
    assert r.status_code == 200
    after = client.get("/api/transactions", params={"q": "ica"}).json()["rows"][0]
    assert after["category_id"] == ovrigt
