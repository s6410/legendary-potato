"""End-to-end-tester för importflödet via HTTP-API:t."""
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


def _make_account(client, name="Testkonto") -> int:
    return client.post("/api/accounts", json={"name": name}).json()["id"]


def _make_profile_from_inspect(client, filename: str, account_id: int) -> int:
    data = (FIXTURES / filename).read_bytes()
    r = client.post("/api/import/inspect", files={"file": (filename, data)})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["known"] is False
    insp = body["inspection"]
    r = client.post(
        "/api/import/profiles",
        json={
            "fingerprint": insp["fingerprint"],
            "name": f"Profil {filename}",
            "file_type": insp["file_type"],
            "column_mapping": insp["suggested_mapping"],
            "default_account_id": account_id,
            "delimiter": insp["delimiter"],
            "encoding": insp["encoding"],
            "decimal_separator": insp["suggested_decimal_separator"],
            "thousands_separator": insp["suggested_thousands_separator"],
            "date_format": insp["suggested_date_format"],
            "header_row_index": insp["header_row_index"],
            "invert_sign": insp["suggested_invert_sign"],
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _upload(client, endpoint: str, filename: str, profile_id: int):
    data = (FIXTURES / filename).read_bytes()
    return client.post(
        f"/api/import/{endpoint}",
        files={"file": (filename, data)},
        data={"profile_id": str(profile_id)},
    )


def test_full_flow_inspect_profile_preview_commit(client):
    acct = _make_account(client)
    profile_id = _make_profile_from_inspect(client, "swedbank.csv", acct)

    preview = _upload(client, "preview", "swedbank.csv", profile_id).json()
    assert preview["total"] == 4
    assert preview["new_count"] == 4
    assert preview["duplicate_count"] == 0

    commit = _upload(client, "commit", "swedbank.csv", profile_id).json()
    assert commit["inserted"] == 4

    # känd profil vid nästa inspect
    data = (FIXTURES / "swedbank.csv").read_bytes()
    r = client.post("/api/import/inspect", files={"file": ("swedbank.csv", data)}).json()
    assert r["known"] is True
    assert r["profile"]["id"] == profile_id

    # identisk fil igen: preview varnar, commit ger 0 nya
    preview2 = _upload(client, "preview", "swedbank.csv", profile_id).json()
    assert preview2["identical_file_already_imported"] is True
    assert preview2["new_count"] == 0
    commit2 = _upload(client, "commit", "swedbank.csv", profile_id).json()
    assert commit2["inserted"] == 0
    assert commit2["duplicates"] == 4


def test_overlapping_exports_dedup_correctly(client):
    acct = _make_account(client)
    profile_id = _make_profile_from_inspect(client, "overlap_a.csv", acct)

    a = _upload(client, "commit", "overlap_a.csv", profile_id).json()
    assert a["inserted"] == 4  # inkl. två identiska kaffeköp

    b = _upload(client, "commit", "overlap_b.csv", profile_id).json()
    # B: 3 dubbletter (två kaffe + SL), 2 nya (Willys + TREDJE kaffet)
    assert b["duplicates"] == 3
    assert b["inserted"] == 2


def test_identical_rows_same_day_both_kept(client):
    acct = _make_account(client)
    profile_id = _make_profile_from_inspect(client, "duplicate_coffee.csv", acct)
    r = _upload(client, "commit", "duplicate_coffee.csv", profile_id).json()
    assert r["inserted"] == 2


def test_revert_batch(client):
    acct = _make_account(client)
    profile_id = _make_profile_from_inspect(client, "nordea.csv", acct)
    commit = _upload(client, "commit", "nordea.csv", profile_id).json()
    assert commit["inserted"] == 4
    assert commit["skipped"] == 1  # Reserverat-raden

    r = client.post(f"/api/import/batches/{commit['batch_id']}/revert")
    assert r.json()["reverted"] == 4

    # efter revert kan samma fil importeras igen
    again = _upload(client, "commit", "nordea.csv", profile_id).json()
    assert again["inserted"] == 4

    batches = client.get("/api/import/batches").json()
    assert {b["status"] for b in batches} == {"committed", "reverted"}


def test_profile_requires_date_and_amount(client):
    r = client.post(
        "/api/import/profiles",
        json={
            "fingerprint": "x", "name": "Trasig", "file_type": "csv",
            "column_mapping": {"description": 1},
        },
    )
    assert r.status_code == 422
