"""Transaktioner: listning med filter, kategorisering, bulkåtgärder, export."""
from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..db.models import Account, CategorizationRule, Category, Transaction, TransactionLink
from ..deps import get_db
from ..services import rules as rules_service
from ..services.categories import category_path

router = APIRouter(prefix="/transactions", tags=["transactions"])


def category_with_children(db: Session, category_id: int) -> list[int]:
    ids = [category_id]
    ids += list(db.scalars(select(Category.id).where(Category.parent_id == category_id)))
    return ids


def _apply_filters(
    stmt,
    db: Session,
    date_from: str | None,
    date_to: str | None,
    account_id: int | None,
    category_id: int | None,
    q: str | None,
    uncategorized: bool,
    min_amount: int | None,
    max_amount: int | None,
    member: str | None = None,
):
    if date_from:
        stmt = stmt.where(Transaction.booked_date >= date_from)
    if date_to:
        stmt = stmt.where(Transaction.booked_date <= date_to)
    if account_id:
        stmt = stmt.where(Transaction.account_id == account_id)
    if category_id:
        stmt = stmt.where(Transaction.category_id.in_(category_with_children(db, category_id)))
    if uncategorized:
        stmt = stmt.where(Transaction.category_id.is_(None))
    if q:
        like = f"%{q.casefold()}%"
        stmt = stmt.where(
            or_(
                func.lower(Transaction.description_raw).like(like),
                Transaction.description_norm.like(like),
                func.lower(func.coalesce(Transaction.note, "")).like(like),
            )
        )
    if min_amount is not None:
        stmt = stmt.where(Transaction.amount_ore >= min_amount)
    if max_amount is not None:
        stmt = stmt.where(Transaction.amount_ore <= max_amount)
    if member is not None:
        if member == "__none__":
            stmt = stmt.where(Transaction.member.is_(None))
        else:
            stmt = stmt.where(Transaction.member == member)
    return stmt


def _link_map(db: Session, txn_ids: list[int]) -> dict[int, dict]:
    if not txn_ids:
        return {}
    out: dict[int, dict] = {}
    for link in db.scalars(
        select(TransactionLink).where(
            TransactionLink.status != "dismissed",
            or_(
                TransactionLink.txn_a_id.in_(txn_ids),
                TransactionLink.txn_b_id.in_(txn_ids),
            ),
        )
    ):
        for tid in (link.txn_a_id, link.txn_b_id):
            out[tid] = {"link_id": link.id, "kind": link.kind, "status": link.status}
    return out


@router.get("")
def list_transactions(
    date_from: str | None = Query(None, alias="from"),
    date_to: str | None = Query(None, alias="to"),
    account_id: int | None = None,
    category_id: int | None = None,
    q: str | None = None,
    uncategorized: bool = False,
    min_amount: int | None = None,
    max_amount: int | None = None,
    member: str | None = None,
    sort: str = "date_desc",
    page: int = 1,
    page_size: int = Query(50, le=500),
    db: Session = Depends(get_db),
) -> dict:
    base = _apply_filters(
        select(Transaction), db, date_from, date_to, account_id, category_id,
        q, uncategorized, min_amount, max_amount, member,
    )
    sub = base.subquery()
    total = db.scalar(select(func.count()).select_from(sub))
    total_amount = db.scalar(select(func.coalesce(func.sum(sub.c.amount_ore), 0)))
    order = {
        "date_desc": (Transaction.booked_date.desc(), Transaction.id.desc()),
        "date_asc": (Transaction.booked_date.asc(), Transaction.id.asc()),
        "amount_desc": (Transaction.amount_ore.desc(),),
        "amount_asc": (Transaction.amount_ore.asc(),),
    }.get(sort, (Transaction.booked_date.desc(), Transaction.id.desc()))
    txns = list(db.scalars(base.order_by(*order).offset((page - 1) * page_size).limit(page_size)))

    cats = {c.id: c for c in db.scalars(select(Category))}
    accounts = {a.id: a.name for a in db.scalars(select(Account))}
    links = _link_map(db, [t.id for t in txns])

    return {
        "total": total,
        "total_amount_ore": total_amount,
        "page": page,
        "page_size": page_size,
        "rows": [
            {
                "id": t.id,
                "booked_date": t.booked_date,
                "amount_ore": t.amount_ore,
                "description": t.description_raw,
                "description_norm": t.description_norm,
                "account_id": t.account_id,
                "account_name": accounts.get(t.account_id),
                "category_id": t.category_id,
                "category_path": category_path(cats, t.category_id),
                "category_source": t.category_source,
                "is_excluded": bool(t.is_excluded),
                "note": t.note,
                "member": t.member,
                "link": links.get(t.id),
            }
            for t in txns
        ],
    }


class TxnPatch(BaseModel):
    category_id: int | None = None
    clear_category: bool = False
    note: str | None = None
    is_excluded: bool | None = None
    member: str | None = None
    clear_member: bool = False


@router.patch("/{txn_id}")
def patch_transaction(txn_id: int, body: TxnPatch, db: Session = Depends(get_db)) -> dict:
    txn = db.get(Transaction, txn_id)
    if not txn:
        raise HTTPException(404, "Transaktionen finns inte")
    if body.clear_category:
        txn.category_id = None
        txn.category_source = None
        txn.applied_rule_id = None
    elif body.category_id is not None:
        if not db.get(Category, body.category_id):
            raise HTTPException(422, "Kategorin finns inte")
        txn.category_id = body.category_id
        txn.category_source = "manual"
        txn.applied_rule_id = None
    if body.note is not None:
        txn.note = body.note or None
    if body.is_excluded is not None:
        txn.is_excluded = int(body.is_excluded)
    if body.clear_member:
        txn.member = None
    elif body.member is not None:
        txn.member = body.member.strip() or None
    return {"ok": True}


class BulkMember(BaseModel):
    ids: list[int]
    member: str | None   # None = rensa


@router.post("/bulk-member")
def bulk_member(body: BulkMember, db: Session = Depends(get_db)) -> dict:
    member = body.member.strip() if body.member else None
    updated = (
        db.query(Transaction)
        .filter(Transaction.id.in_(body.ids))
        .update({"member": member}, synchronize_session=False)
    )
    return {"updated": updated}


@router.get("/members")
def list_members(db: Session = Depends(get_db)) -> list[str]:
    """Kända medlemsnamn: från inställningen + befintliga transaktioner."""
    import json

    from ..db.models import Setting

    names: list[str] = []
    setting = db.get(Setting, "members")
    if setting and setting.value:
        try:
            names = [str(n) for n in json.loads(setting.value)]
        except ValueError:
            names = []
    for (m,) in db.execute(
        select(Transaction.member).where(Transaction.member.isnot(None)).distinct()
    ):
        if m not in names:
            names.append(m)
    return names


class RuleSpec(BaseModel):
    match_type: str = "exact"     # 'exact' | 'prefix' | 'contains'
    pattern: str
    account_specific: bool = False


class BulkCategorize(BaseModel):
    ids: list[int]
    category_id: int
    rule: RuleSpec | None = None


@router.post("/bulk-categorize")
def bulk_categorize(body: BulkCategorize, db: Session = Depends(get_db)) -> dict:
    if not db.get(Category, body.category_id):
        raise HTTPException(422, "Kategorin finns inte")
    txns = list(db.scalars(select(Transaction).where(Transaction.id.in_(body.ids))))
    if not txns:
        raise HTTPException(404, "Inga transaktioner hittades")
    for t in txns:
        t.category_id = body.category_id
        t.category_source = "manual"
        t.applied_rule_id = None

    others_affected = 0
    rule_id = None
    if body.rule:
        if body.rule.match_type not in ("exact", "prefix", "contains"):
            raise HTTPException(422, "Ogiltig regeltyp")
        pattern = body.rule.pattern.strip().casefold()
        if not pattern:
            raise HTTPException(422, "Tomt regelmönster")
        account_id = txns[0].account_id if body.rule.account_specific else None
        rule = db.scalar(
            select(CategorizationRule).where(
                CategorizationRule.match_type == body.rule.match_type,
                CategorizationRule.pattern == pattern,
                CategorizationRule.account_id.is_(None)
                if account_id is None
                else CategorizationRule.account_id == account_id,
            )
        )
        if rule:
            rule.category_id = body.category_id
        else:
            rule = CategorizationRule(
                match_type=body.rule.match_type,
                pattern=pattern,
                category_id=body.category_id,
                account_id=account_id,
            )
            db.add(rule)
        db.flush()
        rule_id = rule.id
        others_affected = rules_service.apply_single_rule(db, rule)

    return {
        "categorized": len(txns),
        "rule_id": rule_id,
        "others_affected": others_affected,
        "suggested_prefix": rules_service.suggest_prefix(txns[0].description_norm),
    }


@router.get("/export.csv")
def export_csv(
    date_from: str | None = Query(None, alias="from"),
    date_to: str | None = Query(None, alias="to"),
    account_id: int | None = None,
    category_id: int | None = None,
    q: str | None = None,
    uncategorized: bool = False,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    stmt = _apply_filters(
        select(Transaction), db, date_from, date_to, account_id, category_id,
        q, uncategorized, None, None,
    ).order_by(Transaction.booked_date.desc())
    cats = {c.id: c for c in db.scalars(select(Category))}
    accounts = {a.id: a.name for a in db.scalars(select(Account))}

    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";")
    writer.writerow(["Datum", "Konto", "Beskrivning", "Belopp", "Huvudkategori", "Underkategori", "Anteckning"])
    for t in db.scalars(stmt):
        cat = cats.get(t.category_id)
        parent = cats.get(cat.parent_id) if cat and cat.parent_id else None
        writer.writerow([
            t.booked_date,
            accounts.get(t.account_id, ""),
            t.description_raw,
            f"{t.amount_ore / 100:.2f}".replace(".", ","),
            (parent.name if parent else (cat.name if cat else "")),
            (cat.name if cat and parent else ""),
            t.note or "",
        ])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue().encode("utf-8-sig")]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=transaktioner.csv"},
    )
