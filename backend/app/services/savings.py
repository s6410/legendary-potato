"""Sparandeberäkningar: drift mot målfördelning och rebalanseringsförslag."""
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


def compute_drift(db: Session) -> dict:
    latest = latest_values(db)
    accounts = list(db.scalars(select(SavingsAccount).where(SavingsAccount.is_active == 1)))
    by_class: dict[str, int] = {}
    for a in accounts:
        val = latest.get(a.id, (None, None))[1]
        if val is not None:
            by_class[a.asset_class] = by_class.get(a.asset_class, 0) + val
    total = sum(by_class.values())
    targets = {t.asset_class: t.target_pct for t in db.scalars(select(TargetAllocation))}

    classes = []
    for asset_class in sorted(set(by_class) | set(targets)):
        value = by_class.get(asset_class, 0)
        current_pct = (value / total * 100) if total else 0.0
        target_pct = targets.get(asset_class)
        classes.append(
            {
                "asset_class": asset_class,
                "label": ASSET_CLASS_LABELS.get(asset_class, asset_class),
                "value_ore": value,
                "current_pct": round(current_pct, 2),
                "target_pct": target_pct,
                "drift_pct": round(current_pct - target_pct, 2) if target_pct is not None else None,
                "drift_ore": round(value - total * target_pct / 100) if target_pct is not None else None,
            }
        )
    return {"total_ore": total, "classes": classes}


def rebalance_plan(db: Session, contribution_ore: int = 0) -> dict:
    """Förslag: hur ska ett nysparande fördelas (eller kapital flyttas) för att
    komma så nära målfördelningen som möjligt?

    Med bidrag: water-filling — fyll underviktade klasser i tur och ordning så
    att ingen försäljning behövs. Utan bidrag: flytta driftbeloppen direkt.
    """
    drift = compute_drift(db)
    targeted = [c for c in drift["classes"] if c["target_pct"] is not None]
    if not targeted or drift["total_ore"] == 0:
        return {"contribution_ore": contribution_ore, "allocations": [], "drift_after": drift}

    if contribution_ore <= 0:
        # ren omflyttning: sälj övervikt, köp undervikt
        allocations = [
            {
                "asset_class": c["asset_class"],
                "label": c["label"],
                "amount_ore": -c["drift_ore"],   # positivt = köp, negativt = sälj
            }
            for c in targeted
            if c["drift_ore"] and abs(c["drift_ore"]) >= 100
        ]
        return {"contribution_ore": 0, "allocations": allocations, "requires_selling": True}

    new_total = drift["total_ore"] + contribution_ore
    # målvärde per klass efter insättningen; köp = max(0, mål - nuvarande)
    wants = {
        c["asset_class"]: max(0.0, new_total * c["target_pct"] / 100 - c["value_ore"])
        for c in targeted
    }
    total_want = sum(wants.values())
    allocations = []
    if total_want <= 0:
        # allt är överviktat — fördela enligt målprocent rakt av
        for c in targeted:
            allocations.append(
                {
                    "asset_class": c["asset_class"],
                    "label": c["label"],
                    "amount_ore": round(contribution_ore * c["target_pct"] / 100),
                }
            )
    else:
        scale = min(1.0, contribution_ore / total_want)
        remaining = contribution_ore
        for c in targeted:
            amount = round(wants[c["asset_class"]] * scale)
            allocations.append(
                {"asset_class": c["asset_class"], "label": c["label"], "amount_ore": amount}
            )
            remaining -= amount
        if remaining != 0 and allocations:
            # avrundningsrest + ev. överskott utöver behoven → enligt målprocent
            if scale >= 1.0:
                for a in allocations:
                    pct = next(c["target_pct"] for c in targeted if c["asset_class"] == a["asset_class"])
                    extra = round(remaining * pct / 100)
                    a["amount_ore"] += extra
                allocations[0]["amount_ore"] += contribution_ore - sum(a["amount_ore"] for a in allocations)
            else:
                allocations[0]["amount_ore"] += remaining

    allocations = [a for a in allocations if a["amount_ore"] > 0]
    return {"contribution_ore": contribution_ore, "allocations": allocations, "requires_selling": False}
