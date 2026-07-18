"""Sparplaner: antaget månadssparande, insatt kapital, prognos och milstolpar.

En plan per toppnivåkonto. Insättningar antas ske samma månadsdag som
startdatumet (dag 29–31 klampas till månadens sista dag). Vid beloppsändring
kedjas planrader: den gamla avslutas och den nya börjar med ackumulerat
insatt kapital i start_value_ore — så förblir historiken korrekt.
"""
from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import SavingsAccount, SavingsPlan, SavingsSnapshot


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
