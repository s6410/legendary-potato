"""Sparplaner: antaget månadssparande, insatt kapital, prognos och milstolpar.

En plan per toppnivåkonto. Insättningar antas ske samma månadsdag som
startdatumet (dag 29–31 klampas till månadens sista dag). Vid beloppsändring
kedjas planrader: den gamla avslutas dagen före den nyas start.

Insatt kapital beräknas alltid live: kontots värde vid första planstarten
(startkapitalet, hämtat ur snapshots vid läsning) plus alla antagna
insättningar. Inget frusets vid skapandet — värden som matas in i efterhand
räknas därmed med, och kolumnen start_value_ore används inte längre.

Utöver planen finns engångsinsättningar (savings_deposits, negativt belopp =
uttag) som räknas in i insatt kapital från sitt datum. Konvention: en
värdepunkt på datum D antas inkludera insättningar gjorda t.o.m. D, så
baslinjen dras ner med engångsinsättningar t.o.m. sin värdepunkts datum för
att undvika dubbelräkning.
"""
from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db.models import SavingsAccount, SavingsDeposit, SavingsPlan, SavingsSnapshot


def deposit_count(start: date, as_of: date) -> int:
    """Antal månadsinsättningar i [start, as_of]; insättning nr 1 sker på startdatumet."""
    if as_of < start:
        return 0
    months = (as_of.year - start.year) * 12 + (as_of.month - start.month)
    due_day = min(start.day, monthrange(as_of.year, as_of.month)[1])
    if as_of.day < due_day:
        months -= 1
    return months + 1


def _leaf_ids(db: Session, account_id: int) -> list[int]:
    child_ids = list(
        db.scalars(select(SavingsAccount.id).where(SavingsAccount.parent_id == account_id))
    )
    return child_ids or [account_id]


def _first_snapshot_date(db: Session, account_id: int) -> str | None:
    return db.scalar(
        select(func.min(SavingsSnapshot.snapshot_date)).where(
            SavingsSnapshot.savings_account_id.in_(_leaf_ids(db, account_id))
        )
    )


def _latest_snapshot_date_until(db: Session, account_id: int, as_of: str) -> str | None:
    return db.scalar(
        select(func.max(SavingsSnapshot.snapshot_date)).where(
            SavingsSnapshot.savings_account_id.in_(_leaf_ids(db, account_id)),
            SavingsSnapshot.snapshot_date <= as_of,
        )
    )


def account_deposits(db: Session, account_id: int) -> list[SavingsDeposit]:
    return list(
        db.scalars(select(SavingsDeposit).where(SavingsDeposit.savings_account_id == account_id))
    )


def _oneoffs_until(deposits: list[SavingsDeposit], as_of_iso: str) -> int:
    return sum(d.amount_ore for d in deposits if d.deposit_date <= as_of_iso)


def _deposits_until(rows: list[SavingsPlan], as_of: date) -> int:
    total = 0
    for row in rows:
        row_start = date.fromisoformat(row.start_date)
        effective = min(as_of, date.fromisoformat(row.end_date)) if row.end_date else as_of
        total += deposit_count(row_start, effective) * row.monthly_amount_ore
    return total


def _baseline(
    db: Session,
    account_id: int,
    rows: list[SavingsPlan],
    deposits: list[SavingsDeposit],
    first_start: date,
) -> int:
    """Startkapitalet: kontots värde vid första starten (plan eller insättning).

    Saknas värden så långt bakåt (starten bakdaterad före första inmatningen)
    antas avkastning 0 fram till första kända värdet: det värdet innehåller
    redan insättningarna gjorda dittills, så baslinjen blir värdet minus dem.
    Engångsinsättningar t.o.m. baslinjens värdepunkt dras alltid av — de ingår
    i värdet och läggs tillbaka i invested_at (ingen dubbelräkning)."""
    first_snap = _first_snapshot_date(db, account_id)
    if first_snap is None:
        return 0
    if first_snap <= first_start.isoformat():
        ref = _latest_snapshot_date_until(db, account_id, first_start.isoformat())
        value = account_value_at(db, account_id, first_start.isoformat())
        return value - _oneoffs_until(deposits, ref)
    snap_date = date.fromisoformat(first_snap)
    value = account_value_at(db, account_id, first_snap)
    return value - _deposits_until(rows, snap_date) - _oneoffs_until(deposits, first_snap)


def invested_at(
    db: Session,
    account_id: int,
    rows: list[SavingsPlan],
    as_of: date,
    deposits: list[SavingsDeposit] | None = None,
) -> int | None:
    """Insatt kapital: startkapitalet + antagna månadsinsättningar +
    engångsinsättningar t.o.m. as_of. None före första planstarten/insättningen."""
    if deposits is None:
        deposits = account_deposits(db, account_id)
    starts = [date.fromisoformat(r.start_date) for r in rows] + [
        date.fromisoformat(d.deposit_date) for d in deposits
    ]
    if not starts:
        return None
    first_start = min(starts)
    if as_of < first_start:
        return None
    baseline = _baseline(db, account_id, rows, deposits, first_start)
    return baseline + _deposits_until(rows, as_of) + _oneoffs_until(deposits, as_of.isoformat())


def account_value_at(db: Session, account_id: int, as_of: str) -> int:
    """Kontots totala värde per datum: summan av lövens senaste snapshot ≤ as_of."""
    total = 0
    for leaf_id in _leaf_ids(db, account_id):
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
    """Skapa eller ersätt aktiv plan.

    Rader som startar på/efter nya startdatumet — eller i samma kalendermånad —
    betraktas som felinmatningar och ersätts helt. Äldre rader avslutas dagen
    före den nya starten (beloppsbyte med bevarad insättningshistorik).
    """
    start = date.fromisoformat(start_date)
    rows = list(
        db.scalars(select(SavingsPlan).where(SavingsPlan.savings_account_id == account_id))
    )
    month = start_date[:7]
    for row in [r for r in rows if r.start_date >= start_date or r.start_date[:7] == month]:
        db.delete(row)
        rows.remove(row)
    day_before = (start - timedelta(days=1)).isoformat()
    for row in rows:
        if row.end_date is None or row.end_date > day_before:
            row.end_date = day_before
    plan = SavingsPlan(
        savings_account_id=account_id,
        monthly_amount_ore=monthly_amount_ore,
        start_date=start_date,
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
    deposits_by_account = _deposits_by_account(db)

    accounts_out = []
    total_invested = total_value = total_monthly = 0
    for account_id, rows in sorted(by_account.items()):
        active = next((r for r in rows if r.end_date is None), None)
        if not active:
            continue
        account = db.get(SavingsAccount, account_id)
        invested = invested_at(db, account_id, rows, today, deposits_by_account.get(account_id, []))
        if invested is None:
            # planen startar i framtiden — dagens värde är startkapitalet
            invested = account_value_at(db, account_id, active.start_date)
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


def _deposits_by_account(db: Session) -> dict[int, list[SavingsDeposit]]:
    grouped: dict[int, list[SavingsDeposit]] = {}
    for dep in db.scalars(select(SavingsDeposit)):
        grouped.setdefault(dep.savings_account_id, []).append(dep)
    return grouped


def invested_series(db: Session, dates: list[str]) -> list[int | None]:
    """Ackumulerat insatt kapital (konton med plan eller engångsinsättningar)
    per datum; None före första planstarten/insättningen."""
    by_account: dict[int, list[SavingsPlan]] = {}
    for row in db.scalars(select(SavingsPlan)):
        by_account.setdefault(row.savings_account_id, []).append(row)
    deposits_by_account = _deposits_by_account(db)
    account_ids = set(by_account) | set(deposits_by_account)
    if not account_ids:
        return [None] * len(dates)
    out: list[int | None] = []
    for d in dates:
        as_of = date.fromisoformat(d)
        values = [
            invested_at(
                db,
                account_id,
                by_account.get(account_id, []),
                as_of,
                deposits_by_account.get(account_id, []),
            )
            for account_id in account_ids
        ]
        known = [v for v in values if v is not None]
        out.append(sum(known) if known else None)
    return out
