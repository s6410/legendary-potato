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
