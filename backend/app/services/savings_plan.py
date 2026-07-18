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
