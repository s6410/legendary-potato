"""Kategoriseringsregler: CRUD, omkörning och rättelsepropagering."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import Account, CategorizationRule, Category, Transaction
from ..db.models import now_iso
from ..deps import get_db
from ..services import rules as rules_service

router = APIRouter(prefix="/rules", tags=["rules"])


def _dict(r: CategorizationRule, cats: dict, accounts: dict) -> dict:
    cat = cats.get(r.category_id)
    parent = cats.get(cat.parent_id) if cat and cat.parent_id else None
    return {
        "id": r.id,
        "match_type": r.match_type,
        "pattern": r.pattern,
        "category_id": r.category_id,
        "category_path": (f"{parent.name} › {cat.name}" if parent else cat.name) if cat else None,
        "account_id": r.account_id,
        "account_name": accounts.get(r.account_id),
        "priority": r.priority,
        "hit_count": r.hit_count,
        "updated_at": r.updated_at,
    }


@router.get("")
def list_rules(db: Session = Depends(get_db)) -> list[dict]:
    cats = {c.id: c for c in db.scalars(select(Category))}
    accounts = {a.id: a.name for a in db.scalars(select(Account))}
    rules = list(db.scalars(select(CategorizationRule).order_by(CategorizationRule.hit_count.desc())))
    return [_dict(r, cats, accounts) for r in rules]


class RuleIn(BaseModel):
    match_type: str
    pattern: str
    category_id: int
    account_id: int | None = None
    priority: int = 0


@router.post("", status_code=201)
def create_rule(body: RuleIn, db: Session = Depends(get_db)) -> dict:
    if body.match_type not in ("exact", "prefix", "contains"):
        raise HTTPException(422, "Ogiltig regeltyp")
    pattern = body.pattern.strip().casefold()
    if not pattern:
        raise HTTPException(422, "Tomt mönster")
    if not db.get(Category, body.category_id):
        raise HTTPException(422, "Kategorin finns inte")
    existing = db.scalar(
        select(CategorizationRule).where(
            CategorizationRule.match_type == body.match_type,
            CategorizationRule.pattern == pattern,
            CategorizationRule.account_id.is_(None)
            if body.account_id is None
            else CategorizationRule.account_id == body.account_id,
        )
    )
    if existing:
        raise HTTPException(409, "En likadan regel finns redan")
    rule = CategorizationRule(
        match_type=body.match_type, pattern=pattern,
        category_id=body.category_id, account_id=body.account_id,
        priority=body.priority,
    )
    db.add(rule)
    db.flush()
    affected = rules_service.apply_single_rule(db, rule)
    cats = {c.id: c for c in db.scalars(select(Category))}
    accounts = {a.id: a.name for a in db.scalars(select(Account))}
    return {**_dict(rule, cats, accounts), "affected": affected}


class RulePatch(BaseModel):
    pattern: str | None = None
    match_type: str | None = None
    category_id: int | None = None
    priority: int | None = None
    propagate: bool = True   # uppdatera regelsatta transaktioner


@router.patch("/{rule_id}")
def update_rule(rule_id: int, body: RulePatch, db: Session = Depends(get_db)) -> dict:
    rule = db.get(CategorizationRule, rule_id)
    if not rule:
        raise HTTPException(404, "Regeln finns inte")
    if body.match_type is not None:
        if body.match_type not in ("exact", "prefix", "contains"):
            raise HTTPException(422, "Ogiltig regeltyp")
        rule.match_type = body.match_type
    if body.pattern is not None:
        p = body.pattern.strip().casefold()
        if not p:
            raise HTTPException(422, "Tomt mönster")
        rule.pattern = p
    if body.category_id is not None:
        if not db.get(Category, body.category_id):
            raise HTTPException(422, "Kategorin finns inte")
        rule.category_id = body.category_id
    if body.priority is not None:
        rule.priority = body.priority
    rule.updated_at = now_iso()
    db.flush()

    affected = 0
    if body.propagate:
        # rättelsepropagering: alla transaktioner som denna regel satt får nya värden
        for txn in db.scalars(
            select(Transaction).where(
                Transaction.applied_rule_id == rule.id,
                Transaction.category_source == "rule",
            )
        ):
            if txn.category_id != rule.category_id:
                txn.category_id = rule.category_id
                affected += 1
        affected += rules_service.apply_single_rule(db, rule)
    return {"ok": True, "affected": affected}


@router.delete("/{rule_id}", status_code=200)
def delete_rule(rule_id: int, clear_transactions: bool = False, db: Session = Depends(get_db)) -> dict:
    rule = db.get(CategorizationRule, rule_id)
    if not rule:
        raise HTTPException(404, "Regeln finns inte")
    cleared = 0
    if clear_transactions:
        cleared = (
            db.query(Transaction)
            .filter(Transaction.applied_rule_id == rule_id, Transaction.category_source == "rule")
            .update(
                {"category_id": None, "category_source": None, "applied_rule_id": None},
                synchronize_session=False,
            )
        )
    else:
        db.query(Transaction).filter(Transaction.applied_rule_id == rule_id).update(
            {"applied_rule_id": None}, synchronize_session=False
        )
    db.delete(rule)
    return {"cleared": cleared}


@router.post("/apply-all")
def apply_all(db: Session = Depends(get_db)) -> dict:
    return {"affected": rules_service.apply_rules_to_uncategorized(db)}
