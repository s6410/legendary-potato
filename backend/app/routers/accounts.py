"""Konton (transaktionskonton — sparkonton ligger under /savings)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db.models import Account, Transaction
from ..deps import get_db

router = APIRouter(prefix="/accounts", tags=["accounts"])


class AccountIn(BaseModel):
    name: str
    kind: str = "checking"
    currency: str = "SEK"


def _dict(a: Account, txn_count: int = 0) -> dict:
    return {
        "id": a.id,
        "name": a.name,
        "kind": a.kind,
        "currency": a.currency,
        "is_active": bool(a.is_active),
        "transaction_count": txn_count,
    }


@router.get("")
def list_accounts(db: Session = Depends(get_db)) -> list[dict]:
    counts = dict(
        db.execute(
            select(Transaction.account_id, func.count()).group_by(Transaction.account_id)
        ).all()
    )
    return [_dict(a, counts.get(a.id, 0)) for a in db.scalars(select(Account).order_by(Account.id))]


@router.post("", status_code=201)
def create_account(body: AccountIn, db: Session = Depends(get_db)) -> dict:
    account = Account(name=body.name, kind=body.kind, currency=body.currency)
    db.add(account)
    db.flush()
    return _dict(account)


@router.patch("/{account_id}")
def update_account(account_id: int, body: dict, db: Session = Depends(get_db)) -> dict:
    account = db.get(Account, account_id)
    if not account:
        raise HTTPException(404, "Kontot finns inte")
    for k in ("name", "kind", "currency", "is_active"):
        if k in body:
            setattr(account, k, int(body[k]) if k == "is_active" else body[k])
    db.flush()
    return _dict(account)


@router.delete("/{account_id}", status_code=204)
def delete_account(account_id: int, db: Session = Depends(get_db)) -> None:
    account = db.get(Account, account_id)
    if not account:
        raise HTTPException(404, "Kontot finns inte")
    has_txns = db.scalar(select(Transaction.id).where(Transaction.account_id == account_id).limit(1))
    if has_txns:
        raise HTTPException(409, "Kontot har transaktioner — inaktivera det i stället")
    db.delete(account)
