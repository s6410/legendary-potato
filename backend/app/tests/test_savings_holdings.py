"""Innehav inom sparkonton: målfördelning per konto, drift och rebalansering."""


def _create(client, name, asset_class="equity", **extra):
    r = client.post("/api/savings/accounts", json={"name": name, "asset_class": asset_class, **extra})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _snapshot(client, date, values):
    r = client.post("/api/savings/snapshots", json={
        "snapshot_date": date,
        "values": [{"savings_account_id": aid, "value_ore": v} for aid, v in values.items()],
    })
    return r


def _setup_isk(client):
    """ISK med två fonder 82/18 (41 000 kr + 9 000 kr) och ett buffertkonto."""
    isk = _create(client, "ISK")
    fond_a = _create(client, "LF Global Indexnära", "equity", parent_id=isk, target_pct=82)
    fond_b = _create(client, "SHB Norden Index", "equity", parent_id=isk, target_pct=18)
    buffert = _create(client, "Buffert", "cash")
    _snapshot(client, "2026-06-30", {fond_a: 4100000, fond_b: 900000, buffert: 5000000})
    return isk, fond_a, fond_b, buffert


class TestHoldings:
    def test_parent_value_is_sum_of_holdings(self, client):
        isk, fond_a, fond_b, _ = _setup_isk(client)
        accounts = {a["id"]: a for a in client.get("/api/savings/accounts").json()}
        assert accounts[isk]["latest_value_ore"] == 5000000
        assert accounts[fond_a]["parent_id"] == isk
        assert accounts[fond_a]["target_pct"] == 82
        assert accounts[fond_b]["target_pct"] == 18

    def test_drift_within_account(self, client):
        isk, fond_a, fond_b, _ = _setup_isk(client)
        drift = client.get("/api/savings/drift").json()
        acct = next(a for a in drift["accounts"] if a["id"] == isk)
        a = next(h for h in acct["holdings"] if h["id"] == fond_a)
        b = next(h for h in acct["holdings"] if h["id"] == fond_b)
        assert a["current_pct"] == 82.0 and a["drift_pct"] == 0.0
        assert b["current_pct"] == 18.0 and b["drift_pct"] == 0.0

        # skjut B ur balans: 41 000 + 19 000 = 60 000 kr
        _snapshot(client, "2026-07-31", {fond_b: 1900000})
        drift = client.get("/api/savings/drift").json()
        acct = next(a for a in drift["accounts"] if a["id"] == isk)
        b = next(h for h in acct["holdings"] if h["id"] == fond_b)
        assert b["current_pct"] == round(1900000 / 6000000 * 100, 2)
        assert b["drift_ore"] == round(1900000 - 6000000 * 0.18)

    def test_by_account_shares_and_classes_over_leaves(self, client):
        isk, *_ = _setup_isk(client)
        drift = client.get("/api/savings/drift").json()
        assert drift["total_ore"] == 10000000
        shares = {a["id"]: a for a in drift["by_account"]}
        assert shares[isk]["share_pct"] == 50.0
        # klassdriften räknas över löven: fonderna (equity) + buffert (cash)
        eq = next(c for c in drift["classes"] if c["asset_class"] == "equity")
        assert eq["value_ore"] == 5000000

    def test_rebalance_per_account_waterfills_holdings(self, client):
        isk, fond_a, fond_b, _ = _setup_isk(client)
        plan = client.get(f"/api/savings/rebalance?account_id={isk}&contribution_ore=1000000").json()
        amounts = {a["id"]: a["amount_ore"] for a in plan["allocations"]}
        # ny total 60 000 kr: mål A 49 200 (köp 8 200), mål B 10 800 (köp 1 800)
        assert amounts[fond_a] == 820000
        assert amounts[fond_b] == 180000

    def test_holdings_targets_put_validates_sum(self, client):
        isk, fond_a, fond_b, _ = _setup_isk(client)
        r = client.put(f"/api/savings/accounts/{isk}/targets", json={
            "targets": [{"id": fond_a, "target_pct": 82}, {"id": fond_b, "target_pct": 10}],
        })
        assert r.status_code == 422
        r = client.put(f"/api/savings/accounts/{isk}/targets", json={
            "targets": [{"id": fond_a, "target_pct": 75}, {"id": fond_b, "target_pct": 25}],
        })
        assert r.status_code == 200, r.text
        accounts = {a["id"]: a for a in client.get("/api/savings/accounts").json()}
        assert accounts[fond_a]["target_pct"] == 75

    def test_delete_parent_cascades_to_holdings(self, client):
        isk, fond_a, fond_b, buffert = _setup_isk(client)
        r = client.delete(f"/api/savings/accounts/{isk}")
        assert r.status_code == 204
        ids = {a["id"] for a in client.get("/api/savings/accounts").json()}
        assert ids == {buffert}


class TestHoldingsValidation:
    def test_snapshot_on_parent_rejected(self, client):
        isk = _create(client, "ISK")
        _create(client, "Fond", parent_id=isk, target_pct=100)
        r = _snapshot(client, "2026-06-30", {isk: 1000000})
        assert r.status_code == 422

    def test_holding_cannot_have_children(self, client):
        isk = _create(client, "ISK")
        fond = _create(client, "Fond", parent_id=isk, target_pct=100)
        r = client.post("/api/savings/accounts", json={"name": "Nested", "parent_id": fond})
        assert r.status_code == 422

    def test_account_with_snapshots_cannot_get_holdings(self, client):
        konto = _create(client, "Gammalt konto")
        _snapshot(client, "2026-06-30", {konto: 1000000})
        r = client.post("/api/savings/accounts", json={"name": "Fond", "parent_id": konto})
        assert r.status_code == 422

    def test_unknown_parent_rejected(self, client):
        r = client.post("/api/savings/accounts", json={"name": "Fond", "parent_id": 999})
        assert r.status_code == 422

    def test_account_cannot_be_its_own_parent(self, client):
        konto = _create(client, "Konto")
        r = client.patch(f"/api/savings/accounts/{konto}", json={"parent_id": konto})
        assert r.status_code == 422

    def test_patch_cannot_set_target_pct_directly(self, client):
        # målen sätts atomiskt via PUT /targets med 100 %-validering — den
        # generiska PATCH:en får inte kunna bryta summainvarianten
        isk = _create(client, "ISK")
        fond = _create(client, "Fond", parent_id=isk, target_pct=100)
        client.patch(f"/api/savings/accounts/{fond}", json={"target_pct": 50})
        accounts = {a["id"]: a for a in client.get("/api/savings/accounts").json()}
        assert accounts[fond]["target_pct"] == 100


class TestDriftBand:
    def _put_targets(self, client, isk, fond_a, fond_b, **extra):
        return client.put(f"/api/savings/accounts/{isk}/targets", json={
            "targets": [{"id": fond_a, "target_pct": 82}, {"id": fond_b, "target_pct": 18}],
            **extra,
        })

    def test_band_persists_and_shows_in_drift(self, client):
        isk, fond_a, fond_b, _ = _setup_isk(client)
        r = self._put_targets(client, isk, fond_a, fond_b, drift_band_pct=4)
        assert r.status_code == 200, r.text
        accounts = {a["id"]: a for a in client.get("/api/savings/accounts").json()}
        assert accounts[isk]["drift_band_pct"] == 4
        drift = client.get("/api/savings/drift").json()
        acct = next(a for a in drift["accounts"] if a["id"] == isk)
        assert acct["band_pct"] == 4

    def test_band_null_clears(self, client):
        isk, fond_a, fond_b, _ = _setup_isk(client)
        self._put_targets(client, isk, fond_a, fond_b, drift_band_pct=4)
        self._put_targets(client, isk, fond_a, fond_b, drift_band_pct=None)
        accounts = {a["id"]: a for a in client.get("/api/savings/accounts").json()}
        assert accounts[isk]["drift_band_pct"] is None

    def test_band_omitted_is_kept(self, client):
        isk, fond_a, fond_b, _ = _setup_isk(client)
        self._put_targets(client, isk, fond_a, fond_b, drift_band_pct=4)
        self._put_targets(client, isk, fond_a, fond_b)
        accounts = {a["id"]: a for a in client.get("/api/savings/accounts").json()}
        assert accounts[isk]["drift_band_pct"] == 4

    def test_band_validation(self, client):
        isk, fond_a, fond_b, _ = _setup_isk(client)
        assert self._put_targets(client, isk, fond_a, fond_b, drift_band_pct=-1).status_code == 422
        assert self._put_targets(client, isk, fond_a, fond_b, drift_band_pct=51).status_code == 422
