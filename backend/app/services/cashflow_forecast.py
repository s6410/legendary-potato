"""Framåtblickande kassaflödesprognos.

Bygger en dag-för-dag-kurva över kommande period utifrån detekterade
återkommande utgifter OCH inkomster (lön, bidrag), plus bufferttid:
hur länge räcker sparandet om inkomsterna försvann?
"""
from __future__ import annotations

from datetime import date, timedelta
from statistics import median

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import Transaction
from . import insights, recurring
from .savings import compute_drift

_GAP_DAYS = {"weekly": 7, "monthly": 30, "quarterly": 91, "yearly": 365}


def _income_series(db: Session, ref: date) -> list[dict]:
    """Månadsvisa POSITIVA serier (lön m.m.) — recurring-motorn tar bara utgifter."""
    cutoff = (ref - timedelta(days=400)).isoformat()
    excluded = insights.excluded_txn_ids(db)
    noise = insights._noise_category_ids(db)
    groups: dict[tuple[str, int], list[Transaction]] = {}
    for t in db.scalars(
        select(Transaction).where(
            Transaction.booked_date >= cutoff,
            Transaction.amount_ore > 0,
            Transaction.is_excluded == 0,
        )
    ):
        if t.id in excluded or t.category_id in noise:
            continue
        groups.setdefault((t.description_norm, t.account_id), []).append(t)

    out = []
    for (norm, _account), txns in groups.items():
        if len(txns) < 3:
            continue
        txns.sort(key=lambda t: t.booked_date)
        dates = [date.fromisoformat(t.booked_date) for t in txns]
        gaps = [(dates[i + 1] - dates[i]).days for i in range(len(dates) - 1)]
        gaps = [g for g in gaps if g > 0]
        if not gaps:
            continue
        med_gap = median(gaps)
        if not 25 <= med_gap <= 35:
            continue
        within = sum(1 for g in gaps if abs(g - med_gap) <= med_gap * 0.2 + 2)
        if within < len(gaps) * 0.7:
            continue
        amounts = [t.amount_ore for t in txns]
        out.append(
            {
                "description": txns[-1].description_raw,
                "median_amount_ore": int(median(amounts)),
                "last_date": dates[-1],
                "gap_days": round(med_gap),
            }
        )
    return out


def forecast_cashflow(db: Session, days: int = 60) -> dict:
    newest = db.scalar(
        select(Transaction.booked_date).order_by(Transaction.booked_date.desc()).limit(1)
    )
    today = date.today()
    ref = max(today, date.fromisoformat(newest)) if newest else today
    horizon = ref + timedelta(days=days)

    events: list[dict] = []

    # utgiftsserier från prenumerationsmotorn
    for s in recurring.detect_recurring(db):
        if s["possibly_ended"]:
            continue
        gap = _GAP_DAYS.get(s["cadence"], 30)
        nxt = date.fromisoformat(s["next_expected_date"])
        while nxt < ref:
            nxt += timedelta(days=gap)
        while nxt <= horizon:
            events.append(
                {
                    "date": nxt.isoformat(),
                    "description": s["display_name"],
                    "amount_ore": -s["median_amount_ore"],
                    "kind": "expense",
                }
            )
            nxt += timedelta(days=gap)

    # inkomstserier (lön etc.)
    for inc in _income_series(db, ref):
        nxt = inc["last_date"] + timedelta(days=inc["gap_days"])
        while nxt < ref:
            nxt += timedelta(days=inc["gap_days"])
        while nxt <= horizon:
            events.append(
                {
                    "date": nxt.isoformat(),
                    "description": inc["description"],
                    "amount_ore": inc["median_amount_ore"],
                    "kind": "income",
                }
            )
            nxt += timedelta(days=inc["gap_days"])

    # övrig rörlig konsumtion: trimmat snitt av senaste hela månadernas
    # utgifter MINUS de återkommande — utsmetad per dag
    fc = insights.forecast(db, 1)
    projected_monthly_expenses = -fc["projected_total_monthly_ore"] if fc["categories"] else 0
    recurring_monthly = sum(
        s["median_amount_ore"] * {"weekly": 4.33, "monthly": 1, "quarterly": 1 / 3, "yearly": 1 / 12}[s["cadence"]]
        for s in recurring.detect_recurring(db)
        if not s["possibly_ended"]
    )
    variable_daily = max(0, (abs(projected_monthly_expenses) - recurring_monthly)) / 30.4

    events.sort(key=lambda e: e["date"])
    daily = []
    cumulative = 0.0
    per_day = {e["date"]: 0 for e in events}
    for e in events:
        per_day[e["date"]] += e["amount_ore"]
    for i in range(1, days + 1):
        d = (ref + timedelta(days=i)).isoformat()
        cumulative += per_day.get(d, 0) - variable_daily
        daily.append({"date": d, "cumulative_ore": round(cumulative)})

    # bufferttid: totalt sparande / genomsnittliga månadsutgifter
    drift = compute_drift(db)
    monthly_burn = abs(projected_monthly_expenses)
    buffer_months = round(drift["total_ore"] / monthly_burn, 1) if monthly_burn else None

    return {
        "from": ref.isoformat(),
        "days": days,
        "events": events,
        "daily": daily,
        "projected_net_ore": round(cumulative),
        "variable_daily_ore": round(variable_daily),
        "savings_total_ore": drift["total_ore"],
        "monthly_expenses_ore": monthly_burn,
        "buffer_months": buffer_months,
    }
