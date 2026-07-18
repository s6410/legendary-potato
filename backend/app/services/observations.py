"""Insiktsmotorn: proaktiva observationer om avvikelser och mönster.

Varje observation: {type, severity, title, body, link} — länken pekar på den
vy i appen där användaren kan agera. Endast de viktigaste returneras.
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy.orm import Session

from . import insights, recurring
from .savings import compute_drift

SPIKE_MIN_ORE = 30000        # 300 kr
SPIKE_MIN_RATIO = 0.30
PRICE_HIKE_RATIO = 1.08
DRIFT_ALERT_PP = 5.0
MAX_OBSERVATIONS = 6


def generate_observations(db: Session, month: str) -> list[dict]:
    obs: list[dict] = []
    f, t = insights.month_range(month)
    _budget_pace(db, month, obs)
    _category_spikes(db, month, obs)
    _recurring_signals(db, month, obs)
    _savings_drift(db, obs)
    _uncategorized(db, f, t, obs)
    obs.sort(key=lambda o: -o["severity"])
    return obs[:MAX_OBSERVATIONS]


def _fmt(ore: int) -> str:
    return f"{round(abs(ore) / 100):,} kr".replace(",", " ")


def _budget_pace(db: Session, month: str, obs: list[dict]) -> None:
    today = date.today()
    f, t = insights.month_range(month)
    month_end = date.fromisoformat(t)
    month_start = date.fromisoformat(f)
    days_total = (month_end - month_start).days + 1
    if today < month_start:
        return
    day_fraction = min(1.0, ((today - month_start).days + 1) / days_total)

    for item in insights.budget_status(db, month):
        progress = item["progress"] or 0
        if progress > 1.0:
            obs.append(
                {
                    "type": "budget_over",
                    "severity": 100,
                    "title": f"Budgeten för {item['category_path']} är överskriden",
                    "body": f"{_fmt(item['spent_ore'])} av {_fmt(item['budget_ore'])} använt "
                            f"({round(progress * 100)} %).",
                    "link": f"/transaktioner?category_id={item['category_id']}&from={f}&to={t}",
                }
            )
        elif progress >= 0.9 and day_fraction < 0.8:
            obs.append(
                {
                    "type": "budget_pace",
                    "severity": 90,
                    "title": f"{item['category_path']} närmar sig budgettaket tidigt",
                    "body": f"{round(progress * 100)} % av budgeten använd men bara "
                            f"{round(day_fraction * 100)} % av månaden har gått.",
                    "link": "/budget",
                }
            )


def _category_spikes(db: Session, month: str, obs: list[dict]) -> None:
    f, t = insights.month_range(month)
    current = {
        b["category_id"]: b
        for b in insights.by_category(db, f, t)
        if b["kind"] == "expense"
    }
    for label, cmp_month in (
        ("förra månaden", insights.shift_month(month, -1)),
        ("samma månad i fjol", insights.shift_month(month, -12)),
    ):
        cf, ct = insights.month_range(cmp_month)
        compare = {
            b["category_id"]: b
            for b in insights.by_category(db, cf, ct)
            if b["kind"] == "expense"
        }
        for cid, bucket in current.items():
            prev = compare.get(cid)
            if not prev or prev["amount_ore"] >= 0:
                continue
            now_abs, prev_abs = abs(bucket["amount_ore"]), abs(prev["amount_ore"])
            diff = now_abs - prev_abs
            if diff >= SPIKE_MIN_ORE and diff >= prev_abs * SPIKE_MIN_RATIO:
                obs.append(
                    {
                        "type": "category_spike",
                        "severity": 70 + min(15, diff // 100000),
                        "title": f"{bucket['name']} är {round(diff / prev_abs * 100)} % dyrare än {label}",
                        "body": f"{_fmt(now_abs)} mot {_fmt(prev_abs)} — en ökning med {_fmt(diff)}.",
                        "link": (
                            f"/transaktioner?category_id={cid}&from={f}&to={t}"
                            if cid is not None
                            else f"/transaktioner?uncategorized=1&from={f}&to={t}"
                        ),
                    }
                )


def _recurring_signals(db: Session, month: str, obs: list[dict]) -> None:
    series = recurring.detect_recurring(db)
    f, _ = insights.month_range(month)
    new_cutoff = (date.fromisoformat(f) - timedelta(days=60)).isoformat()
    for s in series:
        if s["possibly_ended"]:
            obs.append(
                {
                    "type": "recurring_ended",
                    "severity": 40,
                    "title": f"{s['display_name']} verkar ha upphört",
                    "body": f"Ingen dragning sedan {s['last_date']} — om den är uppsagd kan du dölja serien.",
                    "link": "/prenumerationer",
                }
            )
            continue
        if s["first_date"] >= new_cutoff and not s["confirmed"]:
            obs.append(
                {
                    "type": "recurring_new",
                    "severity": 60,
                    "title": f"Ny återkommande kostnad: {s['display_name']}",
                    "body": f"{s['cadence_label']} à {_fmt(s['median_amount_ore'])} "
                            f"≈ {_fmt(s['annual_cost_ore'])}/år.",
                    "link": "/prenumerationer",
                }
            )
        elif s["last_amount_ore"] >= s["median_amount_ore"] * PRICE_HIKE_RATIO:
            hike = s["last_amount_ore"] - s["median_amount_ore"]
            obs.append(
                {
                    "type": "price_hike",
                    "severity": 80,
                    "title": f"{s['display_name']} har höjt priset",
                    "body": f"Senaste dragningen {_fmt(s['last_amount_ore'])} mot normalt "
                            f"{_fmt(s['median_amount_ore'])} (+{_fmt(hike)}).",
                    "link": "/prenumerationer",
                }
            )


def _savings_drift(db: Session, obs: list[dict]) -> None:
    drift = compute_drift(db)
    if not drift["total_ore"]:
        return
    worst = max(
        (c for c in drift["classes"] if c["drift_pct"] is not None),
        key=lambda c: abs(c["drift_pct"]),
        default=None,
    )
    if worst and abs(worst["drift_pct"]) >= DRIFT_ALERT_PP:
        direction = "överviktad" if worst["drift_pct"] > 0 else "underviktad"
        obs.append(
            {
                "type": "savings_drift",
                "severity": 50,
                "title": f"{worst['label']} är {direction} med "
                         f"{str(abs(worst['drift_pct'])).replace('.', ',')} procentenheter",
                "body": f"Avvikelse {_fmt(worst['drift_ore'])} från målfördelningen — "
                        "se rebalanseringsförslaget.",
                "link": "/sparande",
            }
        )


def _uncategorized(db: Session, f: str, t: str, obs: list[dict]) -> None:
    from sqlalchemy import func, select

    from ..db.models import Transaction

    count = db.scalar(
        select(func.count()).where(
            Transaction.booked_date >= f,
            Transaction.booked_date <= t,
            Transaction.category_id.is_(None),
            Transaction.is_excluded == 0,
        )
    )
    if count and count >= 5:
        obs.append(
            {
                "type": "uncategorized",
                "severity": 30,
                "title": f"{count} okategoriserade transaktioner denna period",
                "body": "Kategorisera dem och skapa regler så sköter sig nästa import själv.",
                "link": f"/transaktioner?uncategorized=1&from={f}&to={t}",
            }
        )
