"""Månadsbudgetar per kategori med utfall."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import Budget, Category
from ..deps import get_db
from ..services import insights as insights_svc

router = APIRouter(prefix="/budgets", tags=["budgets"])


@router.get("")
def budget_overview(month: str | None = None, db: Session = Depends(get_db)) -> dict:
    month = month or date.today().strftime("%Y-%m")
    return {"month": month, "items": insights_svc.budget_status(db, month)}


class BudgetIn(BaseModel):
    category_id: int
    amount_ore: int
    valid_from: str | None = None   # 'YYYY-MM', default innevarande månad


@router.post("", status_code=201)
def set_budget(body: BudgetIn, db: Session = Depends(get_db)) -> dict:
    if not db.get(Category, body.category_id):
        raise HTTPException(422, "Kategorin finns inte")
    if body.amount_ore < 0:
        raise HTTPException(422, "Budget måste vara ≥ 0")
    valid_from = body.valid_from or date.today().strftime("%Y-%m")
    existing = db.scalar(
        select(Budget).where(
            Budget.category_id == body.category_id, Budget.valid_from == valid_from
        )
    )
    if existing:
        existing.amount_ore = body.amount_ore
        db.flush()
        return {"id": existing.id}
    b = Budget(category_id=body.category_id, amount_ore=body.amount_ore, valid_from=valid_from)
    db.add(b)
    db.flush()
    return {"id": b.id}


@router.delete("/{budget_id}", status_code=204)
def delete_budget(budget_id: int, db: Session = Depends(get_db)) -> None:
    b = db.get(Budget, budget_id)
    if not b:
        raise HTTPException(404, "Budgeten finns inte")
    db.delete(b)
