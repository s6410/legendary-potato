"""Kvittningar/återbetalningar och kontoöverföringar (transaction_links)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import Account, Transaction, TransactionLink
from ..deps import get_db
from ..services import links as links_service

router = APIRouter(prefix="/links", tags=["links"])


def _txn_dict(t: Transaction, accounts: dict) -> dict:
    return {
        "id": t.id,
        "booked_date": t.booked_date,
        "amount_ore": t.amount_ore,
        "description": t.description_raw,
        "account_name": accounts.get(t.account_id),
    }


@router.get("/suggestions")
def suggestions(db: Session = Depends(get_db)) -> list[dict]:
    accounts = {a.id: a.name for a in db.scalars(select(Account))}
    out = []
    for link in db.scalars(
        select(TransactionLink)
        .where(TransactionLink.status == "suggested")
        .order_by(TransactionLink.score.desc())
    ):
        a = db.get(Transaction, link.txn_a_id)
        b = db.get(Transaction, link.txn_b_id)
        if not a or not b:
            continue
        out.append(
            {
                "id": link.id,
                "kind": link.kind,
                "score": link.score,
                "txn_a": _txn_dict(a, accounts),
                "txn_b": _txn_dict(b, accounts),
            }
        )
    return out


@router.get("/confirmed")
def confirmed(db: Session = Depends(get_db)) -> list[dict]:
    accounts = {a.id: a.name for a in db.scalars(select(Account))}
    out = []
    for link in db.scalars(
        select(TransactionLink).where(TransactionLink.status == "confirmed").order_by(TransactionLink.id.desc())
    ):
        a = db.get(Transaction, link.txn_a_id)
        b = db.get(Transaction, link.txn_b_id)
        if not a or not b:
            continue
        out.append(
            {
                "id": link.id, "kind": link.kind, "score": link.score,
                "txn_a": _txn_dict(a, accounts), "txn_b": _txn_dict(b, accounts),
            }
        )
    return out


@router.post("/{link_id}/confirm")
def confirm(link_id: int, db: Session = Depends(get_db)) -> dict:
    link = db.get(TransactionLink, link_id)
    if not link:
        raise HTTPException(404, "Länken finns inte")
    conflict = db.scalar(
        select(TransactionLink).where(
            TransactionLink.status == "confirmed",
            TransactionLink.id != link.id,
            (TransactionLink.txn_a_id.in_([link.txn_a_id, link.txn_b_id]))
            | (TransactionLink.txn_b_id.in_([link.txn_a_id, link.txn_b_id])),
        )
    )
    if conflict:
        raise HTTPException(409, "En av transaktionerna ingår redan i ett bekräftat par")
    link.status = "confirmed"
    return {"ok": True}


@router.post("/{link_id}/dismiss")
def dismiss(link_id: int, db: Session = Depends(get_db)) -> dict:
    link = db.get(TransactionLink, link_id)
    if not link:
        raise HTTPException(404, "Länken finns inte")
    link.status = "dismissed"
    return {"ok": True}


class ManualLink(BaseModel):
    txn_a_id: int
    txn_b_id: int
    kind: str = "refund"


@router.post("", status_code=201)
def create_manual(body: ManualLink, db: Session = Depends(get_db)) -> dict:
    if body.kind not in ("refund", "transfer"):
        raise HTTPException(422, "Ogiltig länktyp")
    a = db.get(Transaction, body.txn_a_id)
    b = db.get(Transaction, body.txn_b_id)
    if not a or not b or a.id == b.id:
        raise HTTPException(422, "Ogiltiga transaktioner")
    existing = db.scalar(
        select(TransactionLink).where(
            TransactionLink.txn_a_id.in_([a.id, b.id])
            | TransactionLink.txn_b_id.in_([a.id, b.id]),
            TransactionLink.status == "confirmed",
        )
    )
    if existing:
        raise HTTPException(409, "En av transaktionerna är redan länkad")
    link = TransactionLink(kind=body.kind, txn_a_id=a.id, txn_b_id=b.id, status="confirmed")
    db.add(link)
    db.flush()
    return {"id": link.id}


@router.delete("/{link_id}", status_code=204)
def delete_link(link_id: int, db: Session = Depends(get_db)) -> None:
    link = db.get(TransactionLink, link_id)
    if not link:
        raise HTTPException(404, "Länken finns inte")
    db.delete(link)


@router.post("/scan")
def scan(db: Session = Depends(get_db)) -> dict:
    return {"created": links_service.suggest_refunds(db)}
