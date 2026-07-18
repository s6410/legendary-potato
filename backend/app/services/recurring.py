"""Detektering av återkommande utgifter (prenumerationer, räkningar).

Heuristik: ≥3 förekomster av samma normaliserade beskrivning, stabil kadens
(mediangap ±20 % för ≥70 % av gapen) och stabila belopp (±15 %; upp till ±40 %
klassas som "variabel").
"""
from __future__ import annotations

from datetime import date, timedelta
from statistics import median

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import Category, RecurringOverride, Transaction
from .categories import category_path
from .insights import _noise_category_ids, excluded_txn_ids

CADENCES = [
    ("weekly", 6, 8, "Veckovis"),
    ("monthly", 25, 35, "Månadsvis"),
    ("quarterly", 80, 100, "Kvartalsvis"),
    ("yearly", 350, 380, "Årsvis"),
]
_PER_YEAR = {"weekly": 52, "monthly": 12, "quarterly": 4, "yearly": 1}


def detect_recurring(db: Session, reference_date: str | None = None) -> list[dict]:
    newest = reference_date or db.scalar(
        select(Transaction.booked_date).order_by(Transaction.booked_date.desc()).limit(1)
    )
    if not newest:
        return []
    ref = date.fromisoformat(newest)
    cutoff = (ref - timedelta(days=455)).isoformat()  # ~15 månader

    overrides = {
        (o.description_norm, o.account_id): o.status
        for o in db.scalars(select(RecurringOverride))
    }
    cats = {c.id: c for c in db.scalars(select(Category))}

    # samma exkluderingar som övrig statistik: överföringar/exkluderade kategorier
    # och ben i bekräftade kvittningspar är inte återkommande UTGIFTER
    noise = _noise_category_ids(db)
    excluded = excluded_txn_ids(db)
    groups: dict[tuple[str, int], list[Transaction]] = {}
    for t in db.scalars(
        select(Transaction).where(
            Transaction.booked_date >= cutoff,
            Transaction.amount_ore < 0,
            Transaction.is_excluded == 0,
        )
    ):
        if t.id in excluded or t.category_id in noise:
            continue
        groups.setdefault((t.description_norm, t.account_id), []).append(t)

    series: list[dict] = []
    for (norm, account_id), txns in groups.items():
        if len(txns) < 3:
            continue
        override = overrides.get((norm, account_id)) or overrides.get((norm, None))
        if override == "dismissed":
            continue
        txns.sort(key=lambda t: t.booked_date)
        dates = [date.fromisoformat(t.booked_date) for t in txns]
        gaps = [(dates[i + 1] - dates[i]).days for i in range(len(dates) - 1)]
        gaps = [g for g in gaps if g > 0]
        if not gaps:
            continue
        med_gap = median(gaps)

        cadence = None
        for key, lo, hi, label in CADENCES:
            if lo <= med_gap <= hi:
                cadence = (key, label)
                break
        if not cadence:
            continue
        within = sum(1 for g in gaps if abs(g - med_gap) <= med_gap * 0.2 + 2)
        if within < len(gaps) * 0.7:
            continue

        amounts = [abs(t.amount_ore) for t in txns]
        med_amount = median(amounts)
        stable = sum(1 for a in amounts if abs(a - med_amount) <= med_amount * 0.15)
        variable = False
        if stable < len(amounts) * 0.7:
            loosely = sum(1 for a in amounts if abs(a - med_amount) <= med_amount * 0.40)
            if loosely < len(amounts) * 0.7:
                continue
            variable = True

        last = dates[-1]
        next_expected = last + timedelta(days=round(med_gap))
        possibly_ended = (ref - last).days > med_gap * 1.5

        series.append(
            {
                "description_norm": norm,
                "display_name": txns[-1].description_raw,
                "account_id": account_id,
                "cadence": cadence[0],
                "cadence_label": cadence[1],
                "occurrences": len(txns),
                "median_amount_ore": int(med_amount),
                "last_amount_ore": int(abs(txns[-1].amount_ore)),
                "first_date": dates[0].isoformat(),
                "variable_amount": variable,
                "annual_cost_ore": int(med_amount) * _PER_YEAR[cadence[0]],
                "last_date": last.isoformat(),
                "next_expected_date": next_expected.isoformat(),
                "possibly_ended": possibly_ended,
                "category_id": txns[-1].category_id,
                "category_path": category_path(cats, txns[-1].category_id),
                "confirmed": override == "confirmed",
            }
        )
    series.sort(key=lambda s: -s["annual_cost_ore"])
    return series
