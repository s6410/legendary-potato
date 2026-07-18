"""Sammansatt månadsrapport."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import Account, Category
from ..deps import get_db
from ..services import insights as svc
from ..services import recurring as recurring_svc
from ..services.categories import category_path

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/monthly")
def monthly(month: str, db: Session = Depends(get_db)) -> dict:
    if len(month) != 7:
        raise HTTPException(422, "Ange month=YYYY-MM")
    f, t = svc.month_range(month)
    prev = svc.prev_month(month)
    pf, pt = svc.month_range(prev)

    cats = {c.id: c for c in db.scalars(select(Category))}
    accounts = {a.id: a.name for a in db.scalars(select(Account))}
    # samma filtrering som all annan statistik (inkl. överföringskategorier)
    analysis_rows = svc._analysis_rows(db, f, t)
    biggest = [
        {
            "id": txn.id,
            "booked_date": txn.booked_date,
            "amount_ore": txn.amount_ore,
            "description": txn.description_raw,
            "account_name": accounts.get(txn.account_id),
            "category_path": category_path(cats, txn.category_id),
        }
        for txn in sorted(
            (r for r in analysis_rows if r.amount_ore < 0), key=lambda r: r.amount_ore
        )[:10]
    ]

    recurring = recurring_svc.detect_recurring(db)
    upcoming = [
        r for r in recurring
        if not r["possibly_ended"] and r["next_expected_date"][:7] >= month
    ][:10]

    return {
        "month": month,
        "summary": svc.summary(db, f, t),
        "previous_summary": svc.summary(db, pf, pt),
        "by_category": svc.by_category(db, f, t),
        "top_merchants": svc.top_merchants(db, f, t, 10),
        "largest_expenses": biggest,
        "budget": svc.budget_status(db, month),
        "upcoming_recurring": upcoming,
        "trend": svc.trend(db, 12),
    }


@router.get("/yearly")
def yearly(year: int, db: Session = Depends(get_db)) -> dict:
    """"Ditt ekonomiska år" — sammansatt årsberättelse."""
    from sqlalchemy import select as sa_select

    from ..db.models import SavingsAccount, SavingsSnapshot

    f, t = f"{year}-01-01", f"{year}-12-31"
    pf, pt = f"{year - 1}-01-01", f"{year - 1}-12-31"

    months = svc.trend(db, 12, end_month=f"{year}-12")
    summary = svc.summary(db, f, t)
    prev_summary = svc.summary(db, pf, pt)

    current_cats = {
        b["category_id"]: b for b in svc.by_category(db, f, t) if b["kind"] == "expense"
    }
    prev_cats = {
        b["category_id"]: b for b in svc.by_category(db, pf, pt) if b["kind"] == "expense"
    }
    changes = []
    for cid, bucket in current_cats.items():
        prev_amount = abs(prev_cats.get(cid, {}).get("amount_ore", 0))
        now_amount = abs(bucket["amount_ore"])
        if prev_amount == 0 and now_amount < 20000:
            continue
        changes.append(
            {
                "category_id": cid,
                "name": bucket["name"],
                "color": bucket["color"],
                "current_ore": now_amount,
                "previous_ore": prev_amount,
                "diff_ore": now_amount - prev_amount,
            }
        )
    changes.sort(key=lambda c: -abs(c["diff_ore"]))

    # dyraste månaden och dess största kategori
    expense_months = [m for m in months if m["expenses_ore"] < 0]
    biggest_month = min(expense_months, key=lambda m: m["expenses_ore"], default=None)
    biggest_month_top_category = None
    if biggest_month:
        bf, bt = svc.month_range(biggest_month["month"])
        month_cats = [
            b for b in svc.by_category(db, bf, bt) if b["kind"] == "expense" and b["amount_ore"] < 0
        ]
        if month_cats:
            biggest_month_top_category = month_cats[0]

    # prenumerationsfacit
    series = recurring_svc.detect_recurring(db)
    active = [s for s in series if not s["possibly_ended"]]
    cancelled = [s for s in series if s["possibly_ended"] and s["last_date"] >= f]
    cancelled_savings = sum(s["annual_cost_ore"] for s in cancelled)

    # förmögenhetsutveckling: totalvärde vid årets början respektive slut
    def total_at(cutoff: str) -> int | None:
        latest: dict[int, int] = {}
        found = False
        for snap in db.scalars(
            sa_select(SavingsSnapshot)
            .where(SavingsSnapshot.snapshot_date <= cutoff)
            .order_by(SavingsSnapshot.snapshot_date)
        ):
            latest[snap.savings_account_id] = snap.value_ore
            found = True
        if not found:
            return None
        active_ids = {
            a.id for a in db.scalars(sa_select(SavingsAccount).where(SavingsAccount.is_active == 1))
        }
        return sum(v for k, v in latest.items() if k in active_ids)

    savings_start = total_at(f"{year - 1}-12-31")
    savings_end = total_at(t)
    if savings_start is None and savings_end is not None:
        # ingen historik före året — utgå från årets första mätpunkt
        from sqlalchemy import func as sa_func

        first_in_year = db.scalar(
            sa_select(sa_func.min(SavingsSnapshot.snapshot_date)).where(
                SavingsSnapshot.snapshot_date >= f, SavingsSnapshot.snapshot_date <= t
            )
        )
        savings_start = total_at(first_in_year) if first_in_year else None

    savings_rates = [m["savings_rate"] for m in months if m["savings_rate"] is not None]

    return {
        "year": year,
        "summary": summary,
        "previous_summary": prev_summary,
        "months": months,
        "category_changes": changes[:8],
        "biggest_month": biggest_month,
        "biggest_month_top_category": biggest_month_top_category,
        "top_merchants": svc.top_merchants(db, f, t, 10),
        "subscriptions_active": active,
        "subscriptions_cancelled": cancelled,
        "subscriptions_cancelled_savings_ore": cancelled_savings,
        "subscriptions_annual_cost_ore": sum(s["annual_cost_ore"] for s in active),
        "savings_start_ore": savings_start,
        "savings_end_ore": savings_end,
        "avg_savings_rate": round(sum(savings_rates) / len(savings_rates), 4) if savings_rates else None,
    }
