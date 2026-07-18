"""Sparande: konton, manuella värdeögonblicksbilder, målfördelning och drift."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import SavingsAccount, SavingsSnapshot, TargetAllocation
from ..deps import get_db
from ..services import savings as savings_service
from ..services.savings import ASSET_CLASS_LABELS, latest_values as _latest_values

router = APIRouter(prefix="/savings", tags=["savings"])


@router.get("/accounts")
def list_savings_accounts(db: Session = Depends(get_db)) -> list[dict]:
    latest = _latest_values(db)
    accounts = list(
        db.scalars(select(SavingsAccount).order_by(SavingsAccount.sort_order, SavingsAccount.id))
    )
    grouped = savings_service.children_by_parent(accounts)

    def latest_for(a: SavingsAccount) -> tuple[str | None, int | None]:
        kids = grouped.get(a.id)
        if not kids:
            return latest.get(a.id, (None, None))
        dates = [latest[k.id][0] for k in kids if k.id in latest]
        values = [latest[k.id][1] for k in kids if k.id in latest]
        return (max(dates) if dates else None, sum(values) if values else None)

    return [
        {
            "id": a.id,
            "name": a.name,
            "asset_class": a.asset_class,
            "asset_class_label": ASSET_CLASS_LABELS.get(a.asset_class, a.asset_class),
            "is_active": bool(a.is_active),
            "sort_order": a.sort_order,
            "parent_id": a.parent_id,
            "target_pct": a.target_pct,
            "has_holdings": a.id in grouped,
            "latest_date": latest_for(a)[0],
            "latest_value_ore": latest_for(a)[1],
        }
        for a in accounts
    ]


class SavingsAccountIn(BaseModel):
    name: str
    asset_class: str = "other"
    parent_id: int | None = None
    target_pct: float | None = None


def _validate_parent(db: Session, parent_id: int) -> None:
    parent = db.get(SavingsAccount, parent_id)
    if not parent:
        raise HTTPException(422, "Förälderkontot finns inte")
    if parent.parent_id is not None:
        raise HTTPException(422, "Ett innehav kan inte ha egna innehav")
    has_snapshots = db.scalar(
        select(SavingsSnapshot.id)
        .where(SavingsSnapshot.savings_account_id == parent_id)
        .limit(1)
    )
    if has_snapshots:
        raise HTTPException(
            422,
            "Kontot har egna värden — ta bort dem innan innehav läggs till, "
            "annars skulle värdet dubbelräknas",
        )


@router.post("/accounts", status_code=201)
def create_savings_account(body: SavingsAccountIn, db: Session = Depends(get_db)) -> dict:
    if body.parent_id is not None:
        _validate_parent(db, body.parent_id)
    a = SavingsAccount(
        name=body.name,
        asset_class=body.asset_class,
        parent_id=body.parent_id,
        target_pct=body.target_pct,
    )
    db.add(a)
    db.flush()
    return {"id": a.id}


@router.patch("/accounts/{account_id}")
def update_savings_account(account_id: int, body: dict, db: Session = Depends(get_db)) -> dict:
    a = db.get(SavingsAccount, account_id)
    if not a:
        raise HTTPException(404, "Sparkontot finns inte")
    if "parent_id" in body and body["parent_id"] is not None:
        if int(body["parent_id"]) == account_id:
            raise HTTPException(422, "Ett konto kan inte vara sin egen förälder")
        has_children = db.scalar(
            select(SavingsAccount.id).where(SavingsAccount.parent_id == account_id).limit(1)
        )
        if has_children:
            raise HTTPException(422, "Kontot har innehav och kan inte själv bli ett innehav")
        _validate_parent(db, int(body["parent_id"]))
    # target_pct sätts atomiskt via PUT /accounts/{id}/targets (100 %-validering)
    for k in ("name", "asset_class", "is_active", "sort_order", "parent_id"):
        if k in body:
            setattr(a, k, int(body[k]) if k in ("is_active", "sort_order") else body[k])
    return {"ok": True}


class HoldingTargetsIn(BaseModel):
    targets: list[dict]           # [{id, target_pct}]


@router.put("/accounts/{account_id}/targets")
def put_holding_targets(account_id: int, body: HoldingTargetsIn, db: Session = Depends(get_db)) -> dict:
    holdings = {
        h.id: h
        for h in db.scalars(select(SavingsAccount).where(SavingsAccount.parent_id == account_id))
    }
    if not holdings:
        raise HTTPException(404, "Kontot har inga innehav")
    total = sum(float(t.get("target_pct", 0)) for t in body.targets)
    if not (99.0 <= total <= 101.0):
        raise HTTPException(422, f"Målfördelningen måste summera till 100 % (nu {total:.1f} %)")
    for t in body.targets:
        holding = holdings.get(int(t["id"]))
        if not holding:
            raise HTTPException(422, f"Innehav {t['id']} tillhör inte kontot")
        holding.target_pct = float(t["target_pct"])
    return {"ok": True}


@router.delete("/accounts/{account_id}", status_code=204)
def delete_savings_account(account_id: int, db: Session = Depends(get_db)) -> None:
    a = db.get(SavingsAccount, account_id)
    if not a:
        raise HTTPException(404, "Sparkontot finns inte")
    child_ids = list(
        db.scalars(select(SavingsAccount.id).where(SavingsAccount.parent_id == account_id))
    )
    doomed = [account_id, *child_ids]
    db.query(SavingsSnapshot).filter(
        SavingsSnapshot.savings_account_id.in_(doomed)
    ).delete(synchronize_session=False)
    db.query(SavingsAccount).filter(SavingsAccount.id.in_(child_ids)).delete(
        synchronize_session=False
    )
    db.delete(a)


class SnapshotValue(BaseModel):
    savings_account_id: int
    value_ore: int


class SnapshotsIn(BaseModel):
    snapshot_date: str            # 'YYYY-MM-DD'
    values: list[SnapshotValue]


@router.post("/snapshots", status_code=201)
def add_snapshots(body: SnapshotsIn, db: Session = Depends(get_db)) -> dict:
    saved = 0
    for v in body.values:
        account = db.get(SavingsAccount, v.savings_account_id)
        if not account:
            raise HTTPException(422, f"Sparkonto {v.savings_account_id} finns inte")
        has_children = db.scalar(
            select(SavingsAccount.id)
            .where(SavingsAccount.parent_id == v.savings_account_id)
            .limit(1)
        )
        if has_children:
            raise HTTPException(
                422, f"{account.name} har innehav — ange värden på innehaven i stället"
            )
        existing = db.scalar(
            select(SavingsSnapshot).where(
                SavingsSnapshot.savings_account_id == v.savings_account_id,
                SavingsSnapshot.snapshot_date == body.snapshot_date,
            )
        )
        if existing:
            existing.value_ore = v.value_ore
        else:
            db.add(
                SavingsSnapshot(
                    savings_account_id=v.savings_account_id,
                    snapshot_date=body.snapshot_date,
                    value_ore=v.value_ore,
                )
            )
        saved += 1
    return {"saved": saved}


@router.delete("/snapshots/{snapshot_id}", status_code=204)
def delete_snapshot(snapshot_id: int, db: Session = Depends(get_db)) -> None:
    s = db.get(SavingsSnapshot, snapshot_id)
    if not s:
        raise HTTPException(404, "Ögonblicksbilden finns inte")
    db.delete(s)


@router.get("/history")
def history(db: Session = Depends(get_db)) -> dict:
    accounts = {a.id: a for a in db.scalars(select(SavingsAccount))}
    dates = sorted(
        {s.snapshot_date for s in db.scalars(select(SavingsSnapshot))}
    )
    series = []
    for aid, account in accounts.items():
        snaps = {
            s.snapshot_date: s.value_ore
            for s in db.scalars(
                select(SavingsSnapshot).where(SavingsSnapshot.savings_account_id == aid)
            )
        }
        # framåtfyll: senaste kända värde gäller tills nytt anges
        values: list[int | None] = []
        last: int | None = None
        for d in dates:
            if d in snaps:
                last = snaps[d]
            values.append(last)
        series.append(
            {
                "savings_account_id": aid,
                "name": account.name,
                "asset_class": account.asset_class,
                "values": values,
                "snapshots": [
                    {"id": s.id, "date": s.snapshot_date, "value_ore": s.value_ore}
                    for s in db.scalars(
                        select(SavingsSnapshot)
                        .where(SavingsSnapshot.savings_account_id == aid)
                        .order_by(SavingsSnapshot.snapshot_date)
                    )
                ],
            }
        )
    return {"dates": dates, "series": series}


class TargetsIn(BaseModel):
    targets: list[dict]           # [{asset_class, target_pct}]


@router.get("/targets")
def get_targets(db: Session = Depends(get_db)) -> list[dict]:
    return [
        {
            "asset_class": t.asset_class,
            "label": ASSET_CLASS_LABELS.get(t.asset_class, t.asset_class),
            "target_pct": t.target_pct,
        }
        for t in db.scalars(select(TargetAllocation))
    ]


@router.put("/targets")
def put_targets(body: TargetsIn, db: Session = Depends(get_db)) -> dict:
    total = sum(float(t.get("target_pct", 0)) for t in body.targets)
    if body.targets and not (99.0 <= total <= 101.0):
        raise HTTPException(422, f"Målfördelningen måste summera till 100 % (nu {total:.1f} %)")
    db.query(TargetAllocation).delete(synchronize_session=False)
    for t in body.targets:
        db.add(TargetAllocation(asset_class=t["asset_class"], target_pct=float(t["target_pct"])))
    return {"ok": True}


@router.get("/drift")
def drift(db: Session = Depends(get_db)) -> dict:
    return savings_service.compute_drift(db)


@router.get("/rebalance")
def rebalance(
    contribution_ore: int = 0,
    account_id: int | None = None,
    db: Session = Depends(get_db),
) -> dict:
    return savings_service.rebalance_plan(db, contribution_ore, account_id)
