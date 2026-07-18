"""Sparandeberäkningar: drift mot målfördelning och rebalanseringsförslag.

Två nivåer: tillgångsklasser över hela sparandet (target_allocations) och
innehav inom ett konto (savings_accounts.parent_id + target_pct). Värden
finns bara på löv — konton utan innehav, eller innehaven själva.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import SavingsAccount, SavingsSnapshot, TargetAllocation

ASSET_CLASS_LABELS = {
    "equity": "Aktier",
    "fixed_income": "Räntor",
    "cash": "Kontanter",
    "other": "Övrigt",
}


def latest_values(db: Session) -> dict[int, tuple[str, int]]:
    """savings_account_id -> (senaste datum, värde i ören)"""
    out: dict[int, tuple[str, int]] = {}
    for snap in db.scalars(select(SavingsSnapshot).order_by(SavingsSnapshot.snapshot_date)):
        out[snap.savings_account_id] = (snap.snapshot_date, snap.value_ore)
    return out


def children_by_parent(accounts: list[SavingsAccount]) -> dict[int, list[SavingsAccount]]:
    grouped: dict[int, list[SavingsAccount]] = {}
    for a in accounts:
        if a.parent_id is not None:
            grouped.setdefault(a.parent_id, []).append(a)
    return grouped


def _drift_fields(value: int, total: int, target_pct: float | None) -> dict:
    current_pct = (value / total * 100) if total else 0.0
    return {
        "value_ore": value,
        "current_pct": round(current_pct, 2),
        "target_pct": target_pct,
        "drift_pct": round(current_pct - target_pct, 2) if target_pct is not None else None,
        "drift_ore": round(value - total * target_pct / 100) if target_pct is not None else None,
    }


def compute_drift(db: Session) -> dict:
    latest = latest_values(db)
    accounts = list(db.scalars(select(SavingsAccount).where(SavingsAccount.is_active == 1)))
    grouped = children_by_parent(accounts)

    def value_of(a: SavingsAccount) -> int | None:
        return latest.get(a.id, (None, None))[1]

    # klassfördelningen räknas över löven: innehav + konton utan innehav
    leaves = [a for a in accounts if a.id not in grouped]
    by_class: dict[str, int] = {}
    for a in leaves:
        val = value_of(a)
        if val is not None:
            by_class[a.asset_class] = by_class.get(a.asset_class, 0) + val
    total = sum(by_class.values())
    targets = {t.asset_class: t.target_pct for t in db.scalars(select(TargetAllocation))}

    classes = []
    for asset_class in sorted(set(by_class) | set(targets)):
        entry = _drift_fields(by_class.get(asset_class, 0), total, targets.get(asset_class))
        classes.append(
            {
                "asset_class": asset_class,
                "label": ASSET_CLASS_LABELS.get(asset_class, asset_class),
                **entry,
            }
        )

    # toppnivåkonton: andel av totala sparandet + drift mellan innehav
    by_account = []
    account_sections = []
    for a in accounts:
        if a.parent_id is not None:
            continue
        kids = grouped.get(a.id, [])
        kid_values = {k.id: value_of(k) or 0 for k in kids}
        acct_value = sum(kid_values.values()) if kids else (value_of(a) or 0)
        by_account.append(
            {
                "id": a.id,
                "name": a.name,
                "value_ore": acct_value,
                "share_pct": round(acct_value / total * 100, 2) if total else 0.0,
            }
        )
        if kids:
            account_sections.append(
                {
                    "id": a.id,
                    "name": a.name,
                    "total_ore": acct_value,
                    "holdings": [
                        {"id": k.id, "name": k.name, **_drift_fields(kid_values[k.id], acct_value, k.target_pct)}
                        for k in sorted(kids, key=lambda k: (k.sort_order, k.id))
                    ],
                }
            )

    return {"total_ore": total, "classes": classes, "by_account": by_account, "accounts": account_sections}


def _allocate(rows: list[dict], contribution_ore: int) -> dict:
    """Fördela ett bidrag (eller flytta kapital) mot målfördelning.

    rows: [{**ident, "value_ore", "target_pct", "drift_ore"}] där target_pct är satt.
    Med bidrag: water-filling — fyll underviktade rader så inget behöver säljas.
    Utan bidrag: flytta driftbeloppen direkt (positivt = köp, negativt = sälj).
    """
    total = sum(r["value_ore"] for r in rows)
    if not rows or total == 0:
        return {"contribution_ore": contribution_ore, "allocations": [], "requires_selling": False}

    def ident(r: dict) -> dict:
        return {k: v for k, v in r.items() if k not in ("value_ore", "target_pct", "drift_ore")}

    if contribution_ore <= 0:
        allocations = [
            {**ident(r), "amount_ore": -r["drift_ore"]}
            for r in rows
            if r["drift_ore"] and abs(r["drift_ore"]) >= 100
        ]
        return {"contribution_ore": 0, "allocations": allocations, "requires_selling": True}

    new_total = total + contribution_ore
    wants = {id(r): max(0.0, new_total * r["target_pct"] / 100 - r["value_ore"]) for r in rows}
    total_want = sum(wants.values())
    allocations = []
    if total_want <= 0:
        # allt är överviktat — fördela enligt målprocent rakt av
        for r in rows:
            allocations.append({**ident(r), "amount_ore": round(contribution_ore * r["target_pct"] / 100)})
    else:
        scale = min(1.0, contribution_ore / total_want)
        remaining = contribution_ore
        for r in rows:
            amount = round(wants[id(r)] * scale)
            allocations.append({**ident(r), "amount_ore": amount})
            remaining -= amount
        if remaining != 0 and allocations:
            # avrundningsrest + ev. överskott utöver behoven → enligt målprocent
            if scale >= 1.0:
                for a, r in zip(allocations, rows):
                    a["amount_ore"] += round(remaining * r["target_pct"] / 100)
                allocations[0]["amount_ore"] += contribution_ore - sum(a["amount_ore"] for a in allocations)
            else:
                allocations[0]["amount_ore"] += remaining

    allocations = [a for a in allocations if a["amount_ore"] > 0]
    return {"contribution_ore": contribution_ore, "allocations": allocations, "requires_selling": False}


def rebalance_plan(db: Session, contribution_ore: int = 0, account_id: int | None = None) -> dict:
    """Fördelningsförslag — över tillgångsklasser, eller innehaven i ett konto."""
    drift = compute_drift(db)
    if account_id is None:
        rows = [
            {
                "asset_class": c["asset_class"],
                "label": c["label"],
                "value_ore": c["value_ore"],
                "target_pct": c["target_pct"],
                "drift_ore": c["drift_ore"],
            }
            for c in drift["classes"]
            if c["target_pct"] is not None
        ]
    else:
        section = next((a for a in drift["accounts"] if a["id"] == account_id), None)
        rows = [
            {
                "id": h["id"],
                "label": h["name"],
                "value_ore": h["value_ore"],
                "target_pct": h["target_pct"],
                "drift_ore": h["drift_ore"],
            }
            for h in (section["holdings"] if section else [])
            if h["target_pct"] is not None
        ]
    return _allocate(rows, contribution_ore)
