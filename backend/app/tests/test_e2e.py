"""End-to-end: importera fixtur via riktiga HTTP-endpoints → verifiera dashboarddata."""
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


def test_import_to_dashboard_flow(client):
    # 1. inspektera okänd fil → guide-payload
    data = (FIXTURES / "swedbank.csv").read_bytes()
    inspect = client.post("/api/import/inspect", files={"file": ("swedbank.csv", data)}).json()
    assert inspect["known"] is False
    insp = inspect["inspection"]

    # 2. skapa konto + profil (som guiden gör)
    acct = client.post("/api/accounts", json={"name": "Lönekonto"}).json()["id"]
    profile = client.post(
        "/api/import/profiles",
        json={
            "fingerprint": insp["fingerprint"],
            "name": "Swedbank privatkonto",
            "file_type": insp["file_type"],
            "column_mapping": insp["suggested_mapping"],
            "default_account_id": acct,
            "delimiter": insp["delimiter"],
            "encoding": insp["encoding"],
            "decimal_separator": insp["suggested_decimal_separator"],
            "date_format": insp["suggested_date_format"],
            "header_row_index": insp["header_row_index"],
        },
    ).json()

    # 3. preview + commit
    preview = client.post(
        "/api/import/preview",
        files={"file": ("swedbank.csv", data)},
        data={"profile_id": str(profile["id"])},
    ).json()
    assert preview["new_count"] == 4
    commit = client.post(
        "/api/import/commit",
        files={"file": ("swedbank.csv", data)},
        data={"profile_id": str(profile["id"])},
    ).json()
    assert commit["inserted"] == 4

    # 4. dashboardsummering för juni 2026
    summary = client.get("/api/insights/summary", params={"period": "2026-06"}).json()
    assert summary["current"]["income_ore"] == 3520000       # lönen
    assert summary["current"]["expenses_ore"] == -(48250 + 93000 + 35600)
    assert summary["current"]["transaction_count"] == 4

    by_cat = client.get("/api/insights/by-category", params={"period": "2026-06"}).json()
    okat = next(b for b in by_cat if b["name"] == "Okategoriserat")
    assert okat["transaction_count"] == 4  # allt okategoriserat än, även lönen

    merchants = client.get(
        "/api/insights/top-merchants", params={"period": "2026-06"}
    ).json()
    assert merchants[0]["amount_ore"] == -93000  # SL Access störst

    # 5. månadsrapporten är komplett
    report = client.get("/api/reports/monthly", params={"month": "2026-06"}).json()
    assert report["summary"]["net_ore"] == summary["current"]["net_ore"]
    assert len(report["largest_expenses"]) == 3
    assert len(report["trend"]) == 12
