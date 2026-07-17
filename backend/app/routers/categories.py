"""Hierarkiska kategorier (max två nivåer: huvudkategori › underkategori)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db.models import CategorizationRule, Category, Transaction
from ..deps import get_db

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("")
def category_tree(db: Session = Depends(get_db)) -> list[dict]:
    cats = list(db.scalars(select(Category).order_by(Category.sort_order, Category.name)))
    counts = dict(
        db.execute(
            select(Transaction.category_id, func.count()).group_by(Transaction.category_id)
        ).all()
    )
    rule_counts = dict(
        db.execute(
            select(CategorizationRule.category_id, func.count()).group_by(
                CategorizationRule.category_id
            )
        ).all()
    )

    def to_dict(c: Category) -> dict:
        return {
            "id": c.id,
            "name": c.name,
            "kind": c.kind,
            "color": c.color,
            "icon": c.icon,
            "sort_order": c.sort_order,
            "transaction_count": counts.get(c.id, 0),
            "rule_count": rule_counts.get(c.id, 0),
            "children": [],
        }

    roots = [to_dict(c) for c in cats if c.parent_id is None]
    by_id = {r["id"]: r for r in roots}
    for c in cats:
        if c.parent_id is not None and c.parent_id in by_id:
            by_id[c.parent_id]["children"].append(to_dict(c))
    return roots


class CategoryIn(BaseModel):
    name: str
    parent_id: int | None = None
    kind: str | None = None
    color: str | None = None
    icon: str | None = None


@router.post("", status_code=201)
def create_category(body: CategoryIn, db: Session = Depends(get_db)) -> dict:
    kind = body.kind
    if body.parent_id is not None:
        parent = db.get(Category, body.parent_id)
        if not parent:
            raise HTTPException(422, "Föräldrakategorin finns inte")
        if parent.parent_id is not None:
            raise HTTPException(422, "Max två nivåer: underkategorier kan inte ha egna barn")
        kind = kind or parent.kind
    dup = db.scalar(
        select(Category).where(
            Category.name == body.name,
            Category.parent_id.is_(None) if body.parent_id is None
            else Category.parent_id == body.parent_id,
        )
    )
    if dup:
        raise HTTPException(409, "Kategorin finns redan på den nivån")
    cat = Category(
        name=body.name, parent_id=body.parent_id, kind=kind or "expense",
        color=body.color, icon=body.icon,
    )
    db.add(cat)
    db.flush()
    return {"id": cat.id, "name": cat.name, "parent_id": cat.parent_id, "kind": cat.kind}


@router.patch("/{category_id}")
def update_category(category_id: int, body: dict, db: Session = Depends(get_db)) -> dict:
    cat = db.get(Category, category_id)
    if not cat:
        raise HTTPException(404, "Kategorin finns inte")
    for k in ("name", "kind", "color", "icon", "sort_order"):
        if k in body:
            setattr(cat, k, body[k])
    db.flush()
    return {"ok": True}


@router.delete("/{category_id}", status_code=200)
def delete_category(
    category_id: int, reassign_to: int | None = None, db: Session = Depends(get_db)
) -> dict:
    cat = db.get(Category, category_id)
    if not cat:
        raise HTTPException(404, "Kategorin finns inte")
    child_ids = list(db.scalars(select(Category.id).where(Category.parent_id == category_id)))
    all_ids = [category_id] + child_ids
    txn_count = db.scalar(
        select(func.count()).where(Transaction.category_id.in_(all_ids))
    )
    if txn_count and reassign_to is None:
        raise HTTPException(
            409,
            f"Kategorin används av {txn_count} transaktioner — ange reassign_to eller rensa först",
        )
    if reassign_to is not None:
        if reassign_to in all_ids or not db.get(Category, reassign_to):
            raise HTTPException(422, "Ogiltig målkategori")
        db.query(Transaction).filter(Transaction.category_id.in_(all_ids)).update(
            {"category_id": reassign_to, "category_source": "manual"},
            synchronize_session=False,
        )
        db.query(CategorizationRule).filter(
            CategorizationRule.category_id.in_(all_ids)
        ).update({"category_id": reassign_to}, synchronize_session=False)
    else:
        db.query(CategorizationRule).filter(
            CategorizationRule.category_id.in_(all_ids)
        ).delete(synchronize_session=False)
    for cid in child_ids:
        db.delete(db.get(Category, cid))
    db.delete(cat)
    return {"reassigned": txn_count if reassign_to is not None else 0}
