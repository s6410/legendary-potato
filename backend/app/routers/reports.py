"""Sammansatt månadsrapport."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import Account, Category, Transaction
from ..deps import get_db
from ..services import insights as svc
from ..services import recurring as recurring_svc

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/monthly")
def monthly(month: str, db: Session = Depends(get_db)) -> dict:
    if len(month) != 7:
        raise HTTPException(422, "Ange month=YYYY-MM")
    f, t = svc.month_range(month)
    prev = svc.prev_month(month)
    pf, pt = svc.month_range(prev)

    excluded = svc.excluded_txn_ids(db)
    cats = {c.id: c for c in db.scalars(select(Category))}
    accounts = {a.id: a.name for a in db.scalars(select(Account))}
    biggest = [
        {
            "id": txn.id,
            "booked_date": txn.booked_date,
            "amount_ore": txn.amount_ore,
            "description": txn.description_raw,
            "account_name": accounts.get(txn.account_id),
            "category_path": _cat_path(cats, txn.category_id),
        }
        for txn in db.scalars(
            select(Transaction)
            .where(
                Transaction.booked_date >= f,
                Transaction.booked_date <= t,
                Transaction.amount_ore < 0,
                Transaction.is_excluded == 0,
            )
            .order_by(Transaction.amount_ore)
            .limit(15)
        )
        if txn.id not in excluded
    ][:10]

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


def _cat_path(cats: dict, cid: int | None) -> str | None:
    if cid is None or cid not in cats:
        return None
    c = cats[cid]
    if c.parent_id and c.parent_id in cats:
        return f"{cats[c.parent_id].name} › {c.name}"
    return c.name
