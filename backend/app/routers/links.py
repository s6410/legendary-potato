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


def _links_with_txns(db: Session, status: str, order_by) -> list[dict]:
    accounts = {a.id: a.name for a in db.scalars(select(Account))}
    links = list(
        db.scalars(
            select(TransactionLink).where(TransactionLink.status == status).order_by(order_by)
        )
    )
    txn_ids = {l.txn_a_id for l in links} | {l.txn_b_id for l in links}
    txns = {
        t.id: t for t in db.scalars(select(Transaction).where(Transaction.id.in_(txn_ids)))
    }
    out = []
    for link in links:
        a, b = txns.get(link.txn_a_id), txns.get(link.txn_b_id)
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


@router.get("/suggestions")
def suggestions(db: Session = Depends(get_db)) -> list[dict]:
    return _links_with_txns(db, "suggested", TransactionLink.score.desc())


@router.get("/confirmed")
def confirmed(db: Session = Depends(get_db)) -> list[dict]:
    return _links_with_txns(db, "confirmed", TransactionLink.id.desc())


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
    confirmed_elsewhere = db.scalar(
        select(TransactionLink).where(
            TransactionLink.txn_a_id.in_([a.id, b.id])
            | TransactionLink.txn_b_id.in_([a.id, b.id]),
            TransactionLink.status == "confirmed",
        )
    )
    if confirmed_elsewhere:
        raise HTTPException(409, "En av transaktionerna är redan länkad")
    # samma par kan redan finnas som förslag/avfärdat — återanvänd raden i stället
    # för att krocka med UNIQUE(txn_a_id, txn_b_id)
    existing_pair = db.scalar(
        select(TransactionLink).where(
            (
                (TransactionLink.txn_a_id == a.id) & (TransactionLink.txn_b_id == b.id)
            )
            | ((TransactionLink.txn_a_id == b.id) & (TransactionLink.txn_b_id == a.id))
        )
    )
    if existing_pair:
        existing_pair.kind = body.kind
        existing_pair.status = "confirmed"
        db.flush()
        return {"id": existing_pair.id}
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
