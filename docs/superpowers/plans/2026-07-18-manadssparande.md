# Månadssparande Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sparplan per konto (t.ex. 5 000 kr/mån till ISK) som delar upp värdet i insatt kapital vs avkastning, med prognoskort, milstolpar och månatliga köpförslag på Sparande-sidan.

**Architecture:** Ny tabell `savings_plans` med kedjade planrader (beloppsändring avslutar raden och startar en ny med ackumulerat insatt kapital). Ny service `backend/app/services/savings_plan.py` med ren datumlogik + summering; nya endpoints i `routers/savings.py`. Frontend: nya kort i `frontend/src/components/savings/`, befintliga dialoger flyttas dit så `Savings.tsx` krymper.

**Tech Stack:** FastAPI + SQLAlchemy + SQLite (backend), React + TanStack Query + ECharts + Tailwind (frontend), pytest.

**Spec:** `docs/superpowers/specs/2026-07-18-manadssparande-design.md`

## Global Constraints

- All UI-text och kodkommentarer på svenska (följ befintlig stil).
- Belopp lagras i ören (`_ore`-suffix). Procent som `return_pct` är bråkdel (0.083), scenarioprocent (`rate_pct`) är hela procent (7.0).
- Backend-tester körs från `backend/`-mappen: `python -m pytest app/tests/test_savings_plan.py -v`
- Frontendverifiering körs från `frontend/`-mappen: `npm run build` (kör tsc + vite build).
- Inga `console.log`/`print` i produktionskod.
- Filer < 800 rader.
- Commit efter varje task, konventionella commit-prefix (`feat:`, `test:`, `refactor:`).

---

### Task 1: Migration, modell och insättningslogik

**Files:**
- Create: `backend/app/db/migrations/005_savings_plans.sql`
- Modify: `backend/app/db/models.py` (efter `SavingsSnapshot`, rad ~137)
- Create: `backend/app/services/savings_plan.py`
- Create: `backend/app/tests/test_savings_plan.py`

**Interfaces:**
- Produces: modell `SavingsPlan`; `deposit_count(start: date, as_of: date) -> int`; `invested_at(rows: list[SavingsPlan], as_of: date) -> int | None` i `app.services.savings_plan`.

- [ ] **Step 1: Skriv failande tester**

`backend/app/tests/test_savings_plan.py`:

```python
"""Sparplaner: insättningslogik, kedjade rader, nyckeltal, prognos och API."""
from datetime import date

from app.services.savings_plan import deposit_count


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
```

- [ ] **Step 2: Kör testet — ska faila**

Kör: `python -m pytest app/tests/test_savings_plan.py -v` (från `backend/`)
Förväntat: FAIL/ERROR — `ModuleNotFoundError: No module named 'app.services.savings_plan'`

- [ ] **Step 3: Skriv migration**

`backend/app/db/migrations/005_savings_plans.sql`:

```sql
-- Sparplaner: antaget månadssparande per toppnivåkonto. Vid beloppsändring
-- kedjas rader: den aktiva avslutas (end_date) och en ny börjar med
-- ackumulerat insatt kapital i start_value_ore.
CREATE TABLE savings_plans (
    id INTEGER PRIMARY KEY,
    savings_account_id INTEGER NOT NULL REFERENCES savings_accounts(id) ON DELETE CASCADE,
    monthly_amount_ore INTEGER NOT NULL,
    start_date TEXT NOT NULL,
    start_value_ore INTEGER NOT NULL DEFAULT 0,
    end_date TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_savings_plans_account ON savings_plans(savings_account_id);
```

- [ ] **Step 4: Lägg till modellen**

I `backend/app/db/models.py`, direkt efter `SavingsSnapshot`-klassen:

```python
class SavingsPlan(Base):
    __tablename__ = "savings_plans"
    id: Mapped[int] = mapped_column(primary_key=True)
    savings_account_id: Mapped[int] = mapped_column(ForeignKey("savings_accounts.id"))
    monthly_amount_ore: Mapped[int]
    start_date: Mapped[str]
    start_value_ore: Mapped[int] = mapped_column(default=0)
    end_date: Mapped[str | None]
    created_at: Mapped[str] = mapped_column(default=now_iso)
```

- [ ] **Step 5: Skriv servicens kärna**

`backend/app/services/savings_plan.py`:

```python
"""Sparplaner: antaget månadssparande, insatt kapital, prognos och milstolpar.

En plan per toppnivåkonto. Insättningar antas ske samma månadsdag som
startdatumet (dag 29–31 klampas till månadens sista dag). Vid beloppsändring
kedjas planrader: den gamla avslutas och den nya börjar med ackumulerat
insatt kapital i start_value_ore — så förblir historiken korrekt.
"""
from __future__ import annotations

from calendar import monthrange
from datetime import date

from ..db.models import SavingsPlan


def deposit_count(start: date, as_of: date) -> int:
    """Antal månadsinsättningar i [start, as_of]; insättning nr 1 sker på startdatumet."""
    if as_of < start:
        return 0
    months = (as_of.year - start.year) * 12 + (as_of.month - start.month)
    due_day = min(start.day, monthrange(as_of.year, as_of.month)[1])
    if as_of.day < due_day:
        months -= 1
    return months + 1


def _row_invested(plan: SavingsPlan, as_of: date) -> int:
    start = date.fromisoformat(plan.start_date)
    effective = min(as_of, date.fromisoformat(plan.end_date)) if plan.end_date else as_of
    return plan.start_value_ore + deposit_count(start, effective) * plan.monthly_amount_ore


def invested_at(rows: list[SavingsPlan], as_of: date) -> int | None:
    """Insatt kapital enligt (ev. kedjade) planrader; None före första radens start."""
    started = [r for r in rows if date.fromisoformat(r.start_date) <= as_of]
    if not started:
        return None
    latest = max(started, key=lambda r: (r.start_date, r.id))
    return _row_invested(latest, as_of)
```

- [ ] **Step 6: Kör testerna — ska passa**

Kör: `python -m pytest app/tests/test_savings_plan.py -v`
Förväntat: 5 PASS

- [ ] **Step 7: Kör hela sviten (migrationen får inte knäcka något)**

Kör: `python -m pytest -q`
Förväntat: alla gröna

- [ ] **Step 8: Commit**

```bash
git add backend/app/db/migrations/005_savings_plans.sql backend/app/db/models.py backend/app/services/savings_plan.py backend/app/tests/test_savings_plan.py
git commit -m "feat: sparplansmodell med månadsvis insättningslogik"
```

---

### Task 2: Skapa/ersätta/avsluta plan (service)

**Files:**
- Modify: `backend/app/services/savings_plan.py`
- Modify: `backend/app/tests/test_savings_plan.py`

**Interfaces:**
- Consumes: `SavingsPlan`, `invested_at` (Task 1).
- Produces: `account_value_at(db, account_id: int, as_of: str) -> int`, `upsert_plan(db, account_id: int, monthly_amount_ore: int, start_date: str) -> SavingsPlan`, `end_active_plan(db, account_id: int, today: date) -> bool`.

- [ ] **Step 1: Skriv failande tester**

Lägg till i `backend/app/tests/test_savings_plan.py` (överst: utöka importerna):

```python
from sqlalchemy import select

from app.db.models import SavingsAccount, SavingsPlan, SavingsSnapshot
from app.services.savings_plan import (
    account_value_at,
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
    db.add(SavingsSnapshot(savings_account_id=account_id, snapshot_date=snapshot_date, value_ore=value_ore))
    db.flush()


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
```

- [ ] **Step 2: Kör — ska faila**

Kör: `python -m pytest app/tests/test_savings_plan.py -v`
Förväntat: ImportError — `account_value_at` m.fl. finns inte.

- [ ] **Step 3: Implementera**

Lägg till i `backend/app/services/savings_plan.py` (utöka importerna högst upp):

```python
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import SavingsAccount, SavingsPlan, SavingsSnapshot
```

Nya funktioner:

```python
def account_value_at(db: Session, account_id: int, as_of: str) -> int:
    """Kontots totala värde per datum: summan av lövens senaste snapshot ≤ as_of."""
    child_ids = list(
        db.scalars(select(SavingsAccount.id).where(SavingsAccount.parent_id == account_id))
    )
    total = 0
    for leaf_id in child_ids or [account_id]:
        value = db.scalar(
            select(SavingsSnapshot.value_ore)
            .where(
                SavingsSnapshot.savings_account_id == leaf_id,
                SavingsSnapshot.snapshot_date <= as_of,
            )
            .order_by(SavingsSnapshot.snapshot_date.desc())
            .limit(1)
        )
        total += value or 0
    return total


def upsert_plan(db: Session, account_id: int, monthly_amount_ore: int, start_date: str) -> SavingsPlan:
    """Skapa eller ersätt aktiv plan. Kedjar rader så insatt kapital förblir korrekt."""
    start = date.fromisoformat(start_date)
    rows = list(
        db.scalars(select(SavingsPlan).where(SavingsPlan.savings_account_id == account_id))
    )
    # rader som startar på/efter nya startdatumet ersätts helt
    for row in [r for r in rows if r.start_date >= start_date]:
        db.delete(row)
        rows.remove(row)
    day_before = (start - timedelta(days=1)).isoformat()
    prev_invested = invested_at(rows, start - timedelta(days=1))
    for row in rows:
        if row.end_date is None or row.end_date > day_before:
            row.end_date = day_before
    start_value = (
        prev_invested if prev_invested is not None else account_value_at(db, account_id, start_date)
    )
    plan = SavingsPlan(
        savings_account_id=account_id,
        monthly_amount_ore=monthly_amount_ore,
        start_date=start_date,
        start_value_ore=start_value,
    )
    db.add(plan)
    db.flush()
    return plan


def end_active_plan(db: Session, account_id: int, today: date) -> bool:
    """Avsluta kontots aktiva plan. Returnerar False om ingen aktiv plan finns."""
    active = db.scalar(
        select(SavingsPlan).where(
            SavingsPlan.savings_account_id == account_id, SavingsPlan.end_date.is_(None)
        )
    )
    if not active:
        return False
    active.end_date = today.isoformat()
    return True
```

- [ ] **Step 4: Kör — ska passa**

Kör: `python -m pytest app/tests/test_savings_plan.py -v`
Förväntat: alla PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/savings_plan.py backend/app/tests/test_savings_plan.py
git commit -m "feat: skapa/ersätta/avsluta sparplan med kedjade rader"
```

---

### Task 3: API — PUT/DELETE plan

**Files:**
- Modify: `backend/app/routers/savings.py`
- Modify: `backend/app/tests/test_savings_plan.py`

**Interfaces:**
- Consumes: `upsert_plan`, `end_active_plan` (Task 2).
- Produces: `PUT /savings/accounts/{id}/plan` (body `{monthly_amount_ore, start_date?}` → `{id}`), `DELETE /savings/accounts/{id}/plan` (204).

- [ ] **Step 1: Skriv failande API-tester**

Lägg till i `backend/app/tests/test_savings_plan.py`:

```python
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
```

- [ ] **Step 2: Kör — ska faila**

Kör: `python -m pytest app/tests/test_savings_plan.py -k PlanApi -v`
Förväntat: FAIL — 404/405 på PUT (endpointen finns inte).

- [ ] **Step 3: Implementera endpoints**

I `backend/app/routers/savings.py` — utöka importerna:

```python
from datetime import date

from ..services import savings_plan as savings_plan_service
```

Lägg till före `@router.get("/history")`:

```python
class PlanIn(BaseModel):
    monthly_amount_ore: int
    start_date: str | None = None


@router.put("/accounts/{account_id}/plan")
def put_plan(account_id: int, body: PlanIn, db: Session = Depends(get_db)) -> dict:
    account = db.get(SavingsAccount, account_id)
    if not account:
        raise HTTPException(404, "Sparkontot finns inte")
    if account.parent_id is not None:
        raise HTTPException(422, "Sparplaner läggs på kontot, inte på enskilda innehav")
    if body.monthly_amount_ore <= 0:
        raise HTTPException(422, "Månadsbeloppet måste vara större än 0")
    start = body.start_date or date.today().isoformat()
    try:
        date.fromisoformat(start)
    except ValueError:
        raise HTTPException(422, "Ogiltigt startdatum (använd ÅÅÅÅ-MM-DD)")
    plan = savings_plan_service.upsert_plan(db, account_id, body.monthly_amount_ore, start)
    return {"id": plan.id}


@router.delete("/accounts/{account_id}/plan", status_code=204)
def delete_plan(account_id: int, db: Session = Depends(get_db)) -> None:
    if not savings_plan_service.end_active_plan(db, account_id, date.today()):
        raise HTTPException(404, "Kontot har ingen aktiv sparplan")
```

- [ ] **Step 4: Kör — ska passa**

Kör: `python -m pytest app/tests/test_savings_plan.py -v`
Förväntat: alla PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/savings.py backend/app/tests/test_savings_plan.py
git commit -m "feat: API för att skapa och avsluta sparplan"
```

---

### Task 4: plan-summary — nyckeltal, prognos och milstolpar

**Files:**
- Modify: `backend/app/services/savings_plan.py`
- Modify: `backend/app/routers/savings.py`
- Modify: `backend/app/tests/test_savings_plan.py`

**Interfaces:**
- Consumes: `invested_at`, `account_value_at` (Task 1–2).
- Produces: `plan_summary(db, rates: list[float], goal_ore: int | None, today: date) -> dict` och `GET /savings/plan-summary?rates=4,7,10&goal_ore=`. Svar:

```json
{
  "accounts": [{"id": 1, "name": "ISK", "monthly_amount_ore": 500000, "start_date": "2026-07-18",
                 "invested_ore": 0, "current_value_ore": 0, "return_ore": 0, "return_pct": 0.0}],
  "total": {"invested_ore": 0, "current_value_ore": 0, "return_ore": 0, "return_pct": 0.0,
             "monthly_amount_ore": 0},
  "forecast": [{"rate_pct": 7.0, "points": [{"year": 0, "value_ore": 0}]}],
  "milestones": [{"amount_ore": 50000000, "is_goal": false,
                   "reached": [{"rate_pct": 7.0, "date": "2029-03-01"}]}]
}
```
`total` är `null` och listorna tomma när ingen aktiv plan finns. `return_pct` är bråkdel. `reached.date` är `null` om milstolpen inte nås inom 30 år.

- [ ] **Step 1: Skriv failande tester**

Lägg till i `backend/app/tests/test_savings_plan.py` (utöka service-importen med `plan_summary`, `_forecast_series`):

```python
from app.services.savings_plan import _forecast_series, plan_summary


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
```

- [ ] **Step 2: Kör — ska faila**

Kör: `python -m pytest app/tests/test_savings_plan.py -k "Forecast or Summary" -v`
Förväntat: ImportError på `plan_summary`.

- [ ] **Step 3: Implementera i servicen**

Lägg till i `backend/app/services/savings_plan.py`:

```python
MILESTONES_ORE = [
    10_000_000, 25_000_000, 50_000_000, 75_000_000,
    100_000_000, 150_000_000, 200_000_000,
]
MILESTONE_COUNT = 3
FORECAST_YEARS = 30


def _add_months(d: date, months: int) -> date:
    total = d.year * 12 + (d.month - 1) + months
    year, month0 = divmod(total, 12)
    day = min(d.day, monthrange(year, month0 + 1)[1])
    return date(year, month0 + 1, day)


def _forecast_series(start_value: int, monthly_ore: int, rate_pct: float) -> list[int]:
    """Månadsvisa framtida värden, index 0..FORECAST_YEARS*12. Insättning i slutet av varje månad."""
    factor = 1 + rate_pct / 100 / 12
    values = [start_value]
    value = float(start_value)
    for _ in range(FORECAST_YEARS * 12):
        value = value * factor + monthly_ore
        values.append(round(value))
    return values


def plan_summary(db: Session, rates: list[float], goal_ore: int | None, today: date) -> dict:
    all_rows = list(db.scalars(select(SavingsPlan)))
    by_account: dict[int, list[SavingsPlan]] = {}
    for row in all_rows:
        by_account.setdefault(row.savings_account_id, []).append(row)

    accounts_out = []
    total_invested = total_value = total_monthly = 0
    for account_id, rows in sorted(by_account.items()):
        active = next((r for r in rows if r.end_date is None), None)
        if not active:
            continue
        account = db.get(SavingsAccount, account_id)
        invested = invested_at(rows, today) or 0
        value = account_value_at(db, account_id, today.isoformat())
        accounts_out.append(
            {
                "id": account_id,
                "name": account.name,
                "monthly_amount_ore": active.monthly_amount_ore,
                "start_date": active.start_date,
                "invested_ore": invested,
                "current_value_ore": value,
                "return_ore": value - invested,
                "return_pct": round((value - invested) / invested, 4) if invested > 0 else 0.0,
            }
        )
        total_invested += invested
        total_value += value
        total_monthly += active.monthly_amount_ore

    if not accounts_out:
        return {"accounts": [], "total": None, "forecast": [], "milestones": []}

    total = {
        "invested_ore": total_invested,
        "current_value_ore": total_value,
        "return_ore": total_value - total_invested,
        "return_pct": round((total_value - total_invested) / total_invested, 4)
        if total_invested > 0
        else 0.0,
        "monthly_amount_ore": total_monthly,
    }

    series_by_rate = {r: _forecast_series(total_value, total_monthly, r) for r in rates}
    forecast = [
        {
            "rate_pct": rate,
            "points": [
                {"year": y, "value_ore": series[y * 12]} for y in range(FORECAST_YEARS + 1)
            ],
        }
        for rate, series in series_by_rate.items()
    ]

    candidates = [(m, False) for m in MILESTONES_ORE if m > total_value][:MILESTONE_COUNT]
    if goal_ore and goal_ore > total_value and goal_ore not in [m for m, _ in candidates]:
        candidates.append((goal_ore, True))
    milestones = []
    for amount, is_goal in sorted(candidates):
        reached = []
        for rate in rates:
            series = series_by_rate[rate]
            month = next((i for i, v in enumerate(series) if v >= amount), None)
            reached.append(
                {
                    "rate_pct": rate,
                    "date": _add_months(today, month).isoformat() if month is not None else None,
                }
            )
        milestones.append({"amount_ore": amount, "is_goal": is_goal, "reached": reached})

    return {"accounts": accounts_out, "total": total, "forecast": forecast, "milestones": milestones}
```

- [ ] **Step 4: Implementera endpointen**

I `backend/app/routers/savings.py`, efter `delete_plan`:

```python
@router.get("/plan-summary")
def plan_summary(
    rates: str = "4,7,10",
    goal_ore: int | None = None,
    db: Session = Depends(get_db),
) -> dict:
    try:
        rate_list = [float(r) for r in rates.split(",") if r.strip()]
    except ValueError:
        raise HTTPException(422, "Ogiltiga procentsatser")
    if not 1 <= len(rate_list) <= 3 or any(not 0 <= r <= 30 for r in rate_list):
        raise HTTPException(422, "Ange 1–3 procentsatser mellan 0 och 30")
    if goal_ore is not None and goal_ore <= 0:
        raise HTTPException(422, "Målbeloppet måste vara större än 0")
    return savings_plan_service.plan_summary(db, rate_list, goal_ore, date.today())
```

- [ ] **Step 5: Kör — ska passa**

Kör: `python -m pytest app/tests/test_savings_plan.py -v`
Förväntat: alla PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/savings_plan.py backend/app/routers/savings.py backend/app/tests/test_savings_plan.py
git commit -m "feat: plan-summary med nyckeltal, dynamisk prognos och milstolpar"
```

---

### Task 5: Insatt kapital-serie i history + kaskadradering

**Files:**
- Modify: `backend/app/services/savings_plan.py`
- Modify: `backend/app/routers/savings.py:208-245` (history-endpointen)
- Modify: `backend/app/tests/test_savings_plan.py`

**Interfaces:**
- Produces: `invested_series(db, dates: list[str]) -> list[int | None]`; `GET /savings/history` får nytt fält `"invested"` (samma längd som `dates`).

- [ ] **Step 1: Skriv failande tester**

Lägg till i `backend/app/tests/test_savings_plan.py`:

```python
class TestHistoryInvested:
    def test_invested_series_in_history(self, client):
        isk = _create_account(client, "ISK")
        client.post("/api/savings/snapshots", json={
            "snapshot_date": "2026-06-30",
            "values": [{"savings_account_id": isk, "value_ore": 1_000_000}],
        })
        client.put(
            f"/api/savings/accounts/{isk}/plan",
            json={"monthly_amount_ore": 500_000, "start_date": "2026-07-15"},
        )
        client.post("/api/savings/snapshots", json={
            "snapshot_date": "2026-08-31",
            "values": [{"savings_account_id": isk, "value_ore": 2_100_000}],
        })
        h = client.get("/api/savings/history").json()
        assert h["dates"] == ["2026-06-30", "2026-08-31"]
        # före planstart: null; efter: startkapital 1 000 000 + 2 insättningar (15 jul, 15 aug)
        assert h["invested"] == [None, 1_000_000 + 2 * 500_000]

    def test_invested_all_null_without_plans(self, client):
        isk = _create_account(client, "ISK")
        client.post("/api/savings/snapshots", json={
            "snapshot_date": "2026-06-30",
            "values": [{"savings_account_id": isk, "value_ore": 1_000_000}],
        })
        h = client.get("/api/savings/history").json()
        assert h["invested"] == [None]


class TestCascade:
    def test_deleting_account_deletes_plans(self, client, db):
        isk = _create_account(client, "ISK")
        client.put(f"/api/savings/accounts/{isk}/plan", json={"monthly_amount_ore": 500_000})
        client.delete(f"/api/savings/accounts/{isk}")
        assert list(db.scalars(select(SavingsPlan))) == []
```

- [ ] **Step 2: Kör — ska faila**

Kör: `python -m pytest app/tests/test_savings_plan.py -k "History or Cascade" -v`
Förväntat: KeyError/assert på `invested`.

- [ ] **Step 3: Implementera**

I `backend/app/services/savings_plan.py`:

```python
def invested_series(db: Session, dates: list[str]) -> list[int | None]:
    """Ackumulerat insatt kapital (alla konton med plan) per datum; None före första planstart."""
    all_rows = list(db.scalars(select(SavingsPlan)))
    if not all_rows:
        return [None] * len(dates)
    by_account: dict[int, list[SavingsPlan]] = {}
    for row in all_rows:
        by_account.setdefault(row.savings_account_id, []).append(row)
    out: list[int | None] = []
    for d in dates:
        as_of = date.fromisoformat(d)
        values = [invested_at(rows, as_of) for rows in by_account.values()]
        known = [v for v in values if v is not None]
        out.append(sum(known) if known else None)
    return out
```

I `backend/app/routers/savings.py`, ändra history-endpointens sista rad:

```python
    return {"dates": dates, "series": series, "invested": savings_plan_service.invested_series(db, dates)}
```

**Notera kaskadraderingen:** `savings_plans.savings_account_id` har `ON DELETE CASCADE` och `PRAGMA foreign_keys=ON` är satt i `engine.py` — `delete_savings_account` behöver ingen ändring; testet verifierar att det faktiskt fungerar.

- [ ] **Step 4: Kör hela backend-sviten**

Kör: `python -m pytest -q`
Förväntat: alla PASS (befintliga history-tester påverkas inte av det nya fältet).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/savings_plan.py backend/app/routers/savings.py backend/app/tests/test_savings_plan.py
git commit -m "feat: insatt kapital-serie i sparhistoriken"
```

---

### Task 6: Frontend — typer, hooks och utflytt av dialoger

**Files:**
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/api/hooks.ts`
- Create: `frontend/src/components/savings/dialogs.tsx`
- Modify: `frontend/src/pages/Savings.tsx`

**Interfaces:**
- Produces: typerna `SavingsPlanAccount`, `SavingsPlanSummary`; hookarna `useSettings()`, `useSavingsPlanSummary(rates: number[], goalOre?: number | null)`; komponenterna `SnapshotDialog`, `AddAccountDialog`, `AddHoldingDialog`, `TargetsDialog`, `HoldingTargetsDialog` och konstanten `CLASS_OPTIONS` exporterade från `components/savings/dialogs.tsx`.

- [ ] **Step 1: Lägg till typer**

I `frontend/src/api/types.ts` — utöka `SavingsHistory` med fältet `invested`:

```ts
export interface SavingsHistory {
  dates: string[]
  invested: (number | null)[]
  series: {
    savings_account_id: number
    name: string
    asset_class: string
    values: (number | null)[]
    snapshots: { id: number; date: string; value_ore: number }[]
  }[]
}
```

Lägg till efter `Target`-interfacet:

```ts
export interface SavingsPlanAccount {
  id: number
  name: string
  monthly_amount_ore: number
  start_date: string
  invested_ore: number
  current_value_ore: number
  return_ore: number
  return_pct: number
}

export interface SavingsPlanTotal {
  invested_ore: number
  current_value_ore: number
  return_ore: number
  return_pct: number
  monthly_amount_ore: number
}

export interface SavingsPlanSummary {
  accounts: SavingsPlanAccount[]
  total: SavingsPlanTotal | null
  forecast: { rate_pct: number; points: { year: number; value_ore: number }[] }[]
  milestones: {
    amount_ore: number
    is_goal: boolean
    reached: { rate_pct: number; date: string | null }[]
  }[]
}
```

- [ ] **Step 2: Lägg till hooks**

I `frontend/src/api/hooks.ts` — lägg till `SavingsPlanSummary` i typimporten och, efter `useTargets`:

```ts
export const useSettings = () =>
  useQuery({
    queryKey: ['settings'],
    queryFn: () => get<Record<string, string | null>>('/settings'),
  })

export const useSavingsPlanSummary = (rates: number[], goalOre?: number | null) =>
  useQuery({
    queryKey: ['savings', 'plan-summary', rates.join(','), goalOre ?? null],
    queryFn: () =>
      get<SavingsPlanSummary>('/savings/plan-summary', {
        rates: rates.join(','),
        ...(goalOre != null ? { goal_ore: goalOre } : {}),
      }),
    enabled: rates.length > 0,
  })
```

- [ ] **Step 3: Flytta dialogerna**

Skapa `frontend/src/components/savings/dialogs.tsx` och flytta dit — oförändrade — från `frontend/src/pages/Savings.tsx`:

- konstanten `CLASS_OPTIONS` (rad 19–24)
- `SnapshotDialog` (rad 520–584)
- `AddAccountDialog` (rad 586–626)
- `AddHoldingDialog` (rad 628–693)
- `TargetsDialog` (rad 695–750)
- `HoldingTargetsDialog` (rad 350–407)

Filhuvud med importer:

```tsx
import { useState } from 'react'

import { api, useApiMutation, useTargets } from '../../api/hooks'
import type { DriftAccountSection, SavingsAccount } from '../../api/types'
import { parseKr } from '../../lib/format'
import { Modal } from '../Modal'

export const CLASS_OPTIONS = [
  ['equity', 'Aktier'],
  ['fixed_income', 'Räntor'],
  ['cash', 'Kontanter'],
  ['other', 'Övrigt'],
] as const
```

Alla fem komponenterna får `export`-nyckelord. I `Savings.tsx`: ta bort de flyttade komponenterna och `CLASS_OPTIONS`, importera i stället:

```tsx
import {
  AddAccountDialog,
  AddHoldingDialog,
  HoldingTargetsDialog,
  SnapshotDialog,
  TargetsDialog,
} from '../components/savings/dialogs'
```

Rensa bort nu oanvända importer i `Savings.tsx` (`Modal`, `useTargets`, `parseKr` används fortfarande av `RebalanceCard` — behåll det som används; tsc säger till).

- [ ] **Step 4: Verifiera bygget**

Kör: `npm run build` (från `frontend/`)
Förväntat: bygget grönt, inga tsc-fel.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/types.ts frontend/src/api/hooks.ts frontend/src/components/savings/dialogs.tsx frontend/src/pages/Savings.tsx
git commit -m "refactor: flytta sparande-dialoger till egen modul + plan-typer och hooks"
```

---

### Task 7: Månadssparande-kortet och nyckeltalsraden

**Files:**
- Create: `frontend/src/components/savings/PlanCard.tsx`
- Modify: `frontend/src/pages/Savings.tsx`

**Interfaces:**
- Consumes: `useSavingsPlanSummary`, `useRebalance`, typerna från Task 6.
- Produces: `PlanCard({ accounts, planAccounts }: { accounts: SavingsAccount[]; planAccounts: SavingsPlanAccount[] })`.

- [ ] **Step 1: Skriv PlanCard**

`frontend/src/components/savings/PlanCard.tsx`:

```tsx
import { useState } from 'react'

import { api, useApiMutation, useRebalance } from '../../api/hooks'
import type { SavingsAccount, SavingsPlanAccount } from '../../api/types'
import { formatDate, formatOre, parseKr } from '../../lib/format'
import { Modal } from '../Modal'

interface PlanCardProps {
  accounts: SavingsAccount[]
  planAccounts: SavingsPlanAccount[]
}

/** Månadssparande: aktiva sparplaner med månadens köpförslag per innehav. */
export function PlanCard({ accounts, planAccounts }: PlanCardProps) {
  const [editing, setEditing] = useState<SavingsPlanAccount | 'new' | null>(null)
  const topLevel = accounts.filter((a) => a.parent_id == null)
  const planless = topLevel.filter((a) => !planAccounts.some((p) => p.id === a.id))

  return (
    <div className="card mt-5 p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-semibold">Månadssparande</h2>
        {planAccounts.length > 0 && planless.length > 0 && (
          <button onClick={() => setEditing('new')} className="text-sm text-accent hover:underline">
            + Plan för fler konton
          </button>
        )}
      </div>

      {planAccounts.length === 0 ? (
        <div className="mt-3 text-sm text-ink-2">
          <p>
            Ange hur mycket du sätter in varje månad, så följer appen insatt kapital mot
            avkastning och föreslår hur beloppet bör fördelas mellan fonderna.
          </p>
          <button
            onClick={() => setEditing('new')}
            disabled={topLevel.length === 0}
            className="mt-3 rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50"
          >
            Starta månadssparande
          </button>
        </div>
      ) : (
        <div className="mt-3 flex flex-col gap-5">
          {planAccounts.map((p) => (
            <PlanRow key={p.id} plan={p} onEdit={() => setEditing(p)} />
          ))}
        </div>
      )}

      {editing && (
        <PlanDialog
          topLevel={editing === 'new' ? planless : topLevel}
          existing={editing === 'new' ? null : editing}
          onClose={() => setEditing(null)}
        />
      )}
    </div>
  )
}

function PlanRow({ plan, onEdit }: { plan: SavingsPlanAccount; onEdit: () => void }) {
  const { data: buyPlan } = useRebalance(plan.monthly_amount_ore, plan.id)
  const endPlan = useApiMutation(() => api.send('DELETE', `/savings/accounts/${plan.id}/plan`))
  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
        <span>
          <strong>{formatOre(plan.monthly_amount_ore)}/mån</strong> till {plan.name}
          <span className="text-muted"> · sedan {formatDate(plan.start_date)}</span>
        </span>
        <span className="flex gap-3">
          <button onClick={onEdit} className="text-accent hover:underline">
            Ändra
          </button>
          <button
            onClick={() => {
              if (confirm(`Avsluta månadssparandet till ${plan.name}? Historiken behålls.`))
                endPlan.mutate(undefined)
            }}
            className="text-muted hover:text-bad"
          >
            Avsluta
          </button>
        </span>
      </div>
      <div className="mt-1.5 text-sm">
        {buyPlan && buyPlan.allocations.length > 0 ? (
          <ul className="flex flex-col gap-1">
            {buyPlan.allocations.map((a) => (
              <li key={a.id ?? a.label} className="flex justify-between">
                <span className="text-ink-2">{a.label}</span>
                <span className="tabular font-medium">{formatOre(a.amount_ore)}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-muted">Hela beloppet sätts in på kontot.</p>
        )}
      </div>
    </div>
  )
}

function PlanDialog({
  topLevel,
  existing,
  onClose,
}: {
  topLevel: SavingsAccount[]
  existing: SavingsPlanAccount | null
  onClose: () => void
}) {
  const [accountId, setAccountId] = useState<number | undefined>(existing?.id ?? topLevel[0]?.id)
  const [amountText, setAmountText] = useState(
    existing ? String(existing.monthly_amount_ore / 100) : '5000',
  )
  const [startDate, setStartDate] = useState(new Date().toISOString().slice(0, 10))
  const amountOre = parseKr(amountText)
  const mutation = useApiMutation(
    () =>
      api.send('PUT', `/savings/accounts/${accountId}/plan`, {
        monthly_amount_ore: amountOre,
        start_date: startDate,
      }),
    onClose,
  )
  return (
    <Modal title={existing ? `Ändra månadssparande — ${existing.name}` : 'Starta månadssparande'} onClose={onClose}>
      <div className="flex flex-col gap-3 text-sm">
        {!existing && (
          <label className="flex flex-col gap-1">
            <span className="font-medium">Konto</span>
            <select value={accountId} onChange={(e) => setAccountId(Number(e.target.value))}>
              {topLevel.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}
                </option>
              ))}
            </select>
          </label>
        )}
        <label className="flex flex-col gap-1">
          <span className="font-medium">Belopp per månad (kr)</span>
          <input
            inputMode="decimal"
            value={amountText}
            onChange={(e) => setAmountText(e.target.value)}
            autoFocus
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className="font-medium">Startdatum</span>
          <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
          <span className="text-xs text-muted">
            Kontots nuvarande värde räknas som startkapital. Månadsbeloppet fördelas enligt
            kontots målfördelning.
          </span>
        </label>
        {mutation.isError && <span className="text-bad">{(mutation.error as Error).message}</span>}
        <div className="mt-2 flex justify-end gap-3">
          <button onClick={onClose} className="rounded-lg border border-baseline px-4 py-2 hover:bg-grid">
            Avbryt
          </button>
          <button
            disabled={mutation.isPending || accountId == null || amountOre == null || amountOre <= 0}
            onClick={() => mutation.mutate(undefined)}
            className="rounded-lg bg-accent px-4 py-2 font-medium text-white hover:opacity-90 disabled:opacity-50"
          >
            Spara
          </button>
        </div>
      </div>
    </Modal>
  )
}
```

- [ ] **Step 2: Koppla in i sidan + nyckeltalsrad**

I `frontend/src/pages/Savings.tsx`:

Importera:

```tsx
import { useSavingsPlanSummary } from '../api/hooks'   // läggs i befintlig import-lista
import { PlanCard } from '../components/savings/PlanCard'
import { formatPct } from '../lib/format'              // läggs i befintlig import-lista
```

I `SavingsPage`, efter `useDrift()`:

```tsx
const { data: planSummary } = useSavingsPlanSummary([4, 7, 10])
const planTotal = planSummary?.total ?? null
```

(Prognosens dynamiska procentsatser kopplas in i Task 8 — hårdkodningen här är tillfällig och ersätts där.)

Ersätt toppkortet (rad 92–95, `<div className="card mb-5 flex items-baseline ...">...`) med:

```tsx
<div className="card mb-5 px-5 py-4">
  <div className="flex flex-wrap items-baseline justify-between gap-x-8 gap-y-2">
    <div>
      <div className="text-sm text-ink-2">Totalt sparande</div>
      <div className="text-3xl font-bold tabular">{formatOre(drift?.total_ore ?? 0)}</div>
    </div>
    {planTotal && (
      <>
        <div>
          <div className="text-sm text-ink-2">Insatt kapital</div>
          <div className="text-xl font-semibold tabular">{formatOre(planTotal.invested_ore)}</div>
        </div>
        <div>
          <div className="text-sm text-ink-2">Avkastning</div>
          <div
            className={`text-xl font-semibold tabular ${
              planTotal.return_ore >= 0 ? 'text-good' : 'text-bad'
            }`}
          >
            {formatSigned(planTotal.return_ore)} ({formatPct(planTotal.return_pct)})
          </div>
        </div>
      </>
    )}
  </div>
</div>
```

Direkt efter toppkortet (före `<div className="grid gap-5 lg:grid-cols-2">`):

```tsx
<PlanCard accounts={accounts} planAccounts={planSummary?.accounts ?? []} />
```

Obs: `PlanCard` har `mt-5` men ligger nu före grid:en — byt kortets yttre klass i `PlanCard.tsx` till `card mb-5 p-5`.

- [ ] **Step 3: Verifiera bygget**

Kör: `npm run build`
Förväntat: grönt.

- [ ] **Step 4: Manuell verifiering**

Starta appen (`python ../run.py` eller befintligt dev-flöde) och kontrollera på /sparande:
- "Starta månadssparande" syns utan plan; skapa plan 5 000 kr → kortet visar fördelning per fond.
- Toppkortet visar Insatt kapital och Avkastning.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/savings/PlanCard.tsx frontend/src/pages/Savings.tsx
git commit -m "feat: månadssparande-kort med köpförslag och nyckeltalsrad"
```

---

### Task 8: Prognoskort med dynamiska procentsatser + insatt kapital-linje

**Files:**
- Create: `frontend/src/components/savings/ForecastCard.tsx`
- Modify: `frontend/src/pages/Savings.tsx` (historyOption + inkoppling)

**Interfaces:**
- Consumes: `useSettings`, `useSavingsPlanSummary`, `SavingsPlanSummary` (Task 6).
- Produces: `useForecastSettings(): ForecastSettings` och `ForecastCard({ state, summary, tokens })` där `ForecastSettings = { rates: number[]; rateTexts: string[]; setRateText: (i: number, v: string) => void; goalText: string; setGoalText: (v: string) => void; goalOre: number | null; persist: () => void }`.

- [ ] **Step 1: Skriv ForecastCard**

`frontend/src/components/savings/ForecastCard.tsx`:

```tsx
import type { EChartsOption } from 'echarts'
import { useState } from 'react'

import { api, useApiMutation, useSettings } from '../../api/hooks'
import type { SavingsPlanSummary } from '../../api/types'
import { formatMonth, formatOre, parseKr } from '../../lib/format'
import type { chartTokens } from '../../lib/theme'
import { EChart } from '../EChart'

const DEFAULT_RATES = [4, 7, 10]
const MAX_RATE = 30

export interface ForecastSettings {
  rates: number[]
  rateTexts: string[]
  setRateText: (index: number, value: string) => void
  goalText: string
  setGoalText: (value: string) => void
  goalOre: number | null
  persist: () => void
}

function parseRate(text: string): number | null {
  const value = parseFloat(text.replace(',', '.'))
  return Number.isFinite(value) && value >= 0 && value <= MAX_RATE ? value : null
}

/** Procentsatser och målbelopp: läses från inställningarna, sparas vid ändring. */
export function useForecastSettings(): ForecastSettings {
  const { data: settings } = useSettings()
  const [rateDrafts, setRateDrafts] = useState<string[] | null>(null)
  const [goalDraft, setGoalDraft] = useState<string | null>(null)

  const stored = (settings?.savings_forecast_rates ?? '')
    .split(',')
    .map(parseRate)
    .filter((v): v is number => v != null)
  const storedRates = stored.length > 0 ? stored.slice(0, 3) : DEFAULT_RATES
  const rateTexts = rateDrafts ?? storedRates.map((r) => String(r).replace('.', ','))
  const rates = rateTexts.map(parseRate).filter((v): v is number => v != null)

  const storedGoalOre = settings?.savings_goal_ore ? Number(settings.savings_goal_ore) : null
  const goalText = goalDraft ?? (storedGoalOre != null ? String(storedGoalOre / 100) : '')
  const goalOre = parseKr(goalText)

  const save = useApiMutation((body: Record<string, string | null>) =>
    api.send('PUT', '/settings', body),
  )
  const persist = () => {
    if (rates.length === 0) return
    save.mutate({
      savings_forecast_rates: rates.join(','),
      savings_goal_ore: goalOre != null && goalOre > 0 ? String(goalOre) : null,
    })
  }

  return {
    rates,
    rateTexts,
    setRateText: (index, value) => {
      const next = [...rateTexts]
      next[index] = value
      setRateDrafts(next)
    },
    goalText,
    setGoalText: setGoalDraft,
    goalOre,
    persist,
  }
}

interface ForecastCardProps {
  state: ForecastSettings
  summary: SavingsPlanSummary
  tokens: ReturnType<typeof chartTokens>
}

export function ForecastCard({ state, summary, tokens }: ForecastCardProps) {
  const emphasized = Math.floor(summary.forecast.length / 2)
  return (
    <div className="card mt-5 p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="font-semibold">Prognos</h2>
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className="text-ink-2">Årlig avkastning</span>
          {state.rateTexts.map((text, i) => (
            <span key={i} className="flex items-center gap-1">
              <input
                inputMode="decimal"
                className="w-14 text-right"
                value={text}
                onChange={(e) => state.setRateText(i, e.target.value)}
                onBlur={state.persist}
                aria-label={`Scenario ${i + 1} (%)`}
              />
              %
            </span>
          ))}
          <span className="ml-3 text-ink-2">Målbelopp</span>
          <input
            inputMode="decimal"
            className="w-28 text-right"
            placeholder="valfritt"
            value={state.goalText}
            onChange={(e) => state.setGoalText(e.target.value)}
            onBlur={state.persist}
            aria-label="Eget målbelopp (kr)"
          />
          <span>kr</span>
        </div>
      </div>

      {summary.forecast.length > 0 && (
        <EChart height={280} option={forecastOption(summary, tokens, emphasized)} />
      )}

      {summary.milestones.length > 0 && (
        <ul className="mt-3 flex flex-col gap-1 text-sm">
          {summary.milestones.map((m) => {
            const mid = m.reached[emphasized] ?? m.reached[0]
            return (
              <li key={m.amount_ore} className="flex justify-between">
                <span className={m.is_goal ? 'font-medium' : 'text-ink-2'}>
                  {m.is_goal ? 'Ditt mål: ' : ''}
                  {formatOre(m.amount_ore)}
                </span>
                <span className="tabular text-ink-2">
                  {mid.date
                    ? `nås ca ${formatMonth(mid.date.slice(0, 7))} vid ${String(mid.rate_pct).replace('.', ',')} %`
                    : `nås inte inom 30 år vid ${String(mid.rate_pct).replace('.', ',')} %`}
                </span>
              </li>
            )
          })}
        </ul>
      )}
      <p className="mt-2 text-xs text-muted">
        Antar månadssparande enligt planen och jämn avkastning — verkligheten svänger mer.
      </p>
    </div>
  )
}

function forecastOption(
  summary: SavingsPlanSummary,
  t: ReturnType<typeof chartTokens>,
  emphasized: number,
): EChartsOption {
  const startYear = new Date().getFullYear()
  const years = summary.forecast[0].points.map((p) => String(startYear + p.year))
  return {
    textStyle: { color: t.ink2 },
    legend: { textStyle: { color: t.ink2, fontSize: 11 }, top: 0 },
    grid: { left: 8, right: 8, top: 32, bottom: 4, containLabel: true },
    tooltip: {
      trigger: 'axis',
      backgroundColor: t.surface,
      borderColor: t.grid,
      textStyle: { color: t.ink, fontSize: 12 },
      valueFormatter: (v) => (v == null ? '–' : formatOre(Number(v))),
    },
    xAxis: {
      type: 'category',
      data: years,
      axisLine: { lineStyle: { color: t.baseline } },
      axisTick: { show: false },
      axisLabel: { color: t.muted, fontSize: 10 },
    },
    yAxis: {
      type: 'value',
      axisLabel: { color: t.muted, fontSize: 10, formatter: (v: number) => formatOre(v) },
      splitLine: { lineStyle: { color: t.grid } },
    },
    series: summary.forecast.map((f, i) => ({
      name: `${String(f.rate_pct).replace('.', ',')} %`,
      type: 'line',
      data: f.points.map((p) => p.value_ore),
      symbol: 'none',
      lineStyle: { width: i === emphasized ? 3 : 1.5 },
      itemStyle: { color: t.series[i % t.series.length] },
      color: t.series[i % t.series.length],
    })),
  }
}
```

- [ ] **Step 2: Koppla in i sidan + insatt kapital-linjen**

I `frontend/src/pages/Savings.tsx`:

```tsx
import { ForecastCard, useForecastSettings } from '../components/savings/ForecastCard'
```

Ersätt Task 7:s tillfälliga rader i `SavingsPage`:

```tsx
const forecastSettings = useForecastSettings()
const { data: planSummary } = useSavingsPlanSummary(
  forecastSettings.rates,
  forecastSettings.goalOre != null && forecastSettings.goalOre > 0 ? forecastSettings.goalOre : undefined,
)
const planTotal = planSummary?.total ?? null
```

Efter historikgrafens block (rad ~150–155) lägg till:

```tsx
{planSummary && planSummary.accounts.length > 0 && (
  <ForecastCard state={forecastSettings} summary={planSummary} tokens={tokens} />
)}
```

I `historyOption` — ändra `series` så att insatt kapital-linjen läggs till efter kontoserierna:

```tsx
series: [
  ...history.series.map((s, i) => ({
    name: s.name,
    type: 'line' as const,
    stack: 'total',
    areaStyle: { opacity: 0.35 },
    lineStyle: { width: 2 },
    symbol: 'circle',
    symbolSize: 5,
    itemStyle: { color: t.series[i % t.series.length] },
    color: t.series[i % t.series.length],
    data: s.values,
    connectNulls: true,
  })),
  ...(history.invested.some((v) => v != null)
    ? [
        {
          name: 'Insatt kapital',
          type: 'line' as const,
          data: history.invested,
          symbol: 'none' as const,
          lineStyle: { width: 2, type: 'dashed' as const, color: t.ink },
          itemStyle: { color: t.ink },
          z: 5,
        },
      ]
    : []),
],
```

- [ ] **Step 3: Verifiera bygget**

Kör: `npm run build`
Förväntat: grönt.

- [ ] **Step 4: Manuell verifiering**

I appen på /sparande med en plan skapad:
- Prognoskortet visar tre banor; ändra en procentsats → grafen uppdateras direkt och värdet ligger kvar efter sidomladdning (persist via inställningar).
- Sätt målbelopp → egen milstolpsrad visas.
- Historikgrafen visar streckad "Insatt kapital"-linje.

- [ ] **Step 5: Kör allt en sista gång**

Kör: `python -m pytest -q` (från `backend/`) och `npm run build` (från `frontend/`)
Förväntat: allt grönt.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/savings/ForecastCard.tsx frontend/src/pages/Savings.tsx
git commit -m "feat: prognoskort med dynamiska scenarier, målbelopp och insatt kapital-linje"
```
