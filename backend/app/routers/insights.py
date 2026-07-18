"""Insikter: KPI:er, kategorifördelning, trender, kassaflöde, prognos."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..db.models import RecurringOverride
from ..deps import get_db
from ..services import insights as svc
from ..services import recurring as recurring_svc

router = APIRouter(prefix="/insights", tags=["insights"])


def _range(
    period: str | None, date_from: str | None, date_to: str | None
) -> tuple[str, str]:
    if period:
        return svc.month_range(period)
    if date_from and date_to:
        return date_from, date_to
    raise HTTPException(422, "Ange period=YYYY-MM eller from+to")


@router.get("/summary")
def summary(
    period: str | None = None,
    date_from: str | None = Query(None, alias="from"),
    date_to: str | None = Query(None, alias="to"),
    compare: bool = True,
    include_refunds: bool = False,
    db: Session = Depends(get_db),
) -> dict:
    f, t = _range(period, date_from, date_to)
    current = svc.summary(db, f, t, include_refunds)
    result = {"from": f, "to": t, "current": current, "previous": None}
    if compare and period:
        pf, pt = svc.month_range(svc.prev_month(period))
        result["previous"] = svc.summary(db, pf, pt, include_refunds)
    elif compare:
        # jämför med lika lång period direkt före
        from datetime import date, timedelta

        d_from, d_to = date.fromisoformat(f), date.fromisoformat(t)
        span = (d_to - d_from).days + 1
        result["previous"] = svc.summary(
            db,
            (d_from - timedelta(days=span)).isoformat(),
            (d_from - timedelta(days=1)).isoformat(),
            include_refunds,
        )
    return result


@router.get("/by-category")
def by_category(
    period: str | None = None,
    date_from: str | None = Query(None, alias="from"),
    date_to: str | None = Query(None, alias="to"),
    parent_id: int | None = None,
    include_refunds: bool = False,
    db: Session = Depends(get_db),
) -> list[dict]:
    f, t = _range(period, date_from, date_to)
    return svc.by_category(db, f, t, parent_id, include_refunds)


@router.get("/trend")
def trend(
    months: int = Query(12, le=60),
    category_id: int | None = None,
    include_refunds: bool = False,
    db: Session = Depends(get_db),
) -> list[dict]:
    return svc.trend(db, months, category_id, include_refunds)


@router.get("/cashflow")
def cashflow(
    months: int = Query(12, le=60),
    include_refunds: bool = False,
    db: Session = Depends(get_db),
) -> list[dict]:
    return svc.cashflow(db, months, include_refunds)


@router.get("/top-merchants")
def top_merchants(
    period: str | None = None,
    date_from: str | None = Query(None, alias="from"),
    date_to: str | None = Query(None, alias="to"),
    limit: int = Query(10, le=50),
    include_refunds: bool = False,
    db: Session = Depends(get_db),
) -> list[dict]:
    f, t = _range(period, date_from, date_to)
    return svc.top_merchants(db, f, t, limit, include_refunds)


@router.get("/recurring")
def recurring(db: Session = Depends(get_db)) -> list[dict]:
    return recurring_svc.detect_recurring(db)


@router.post("/recurring/override")
def recurring_override(body: dict, db: Session = Depends(get_db)) -> dict:
    norm = body.get("description_norm")
    status = body.get("status")
    if not norm or status not in ("confirmed", "dismissed"):
        raise HTTPException(422, "description_norm och status (confirmed/dismissed) krävs")
    from sqlalchemy import select

    account_id = body.get("account_id")
    existing = db.scalar(
        select(RecurringOverride).where(
            RecurringOverride.description_norm == norm,
            RecurringOverride.account_id.is_(None)
            if account_id is None
            else RecurringOverride.account_id == account_id,
        )
    )
    if existing:
        existing.status = status
    else:
        db.add(RecurringOverride(description_norm=norm, account_id=account_id, status=status))
    return {"ok": True}


@router.get("/forecast")
def forecast(months: int = Query(3, le=12), db: Session = Depends(get_db)) -> dict:
    return svc.forecast(db, months)


@router.get("/observations")
def observations(month: str, db: Session = Depends(get_db)) -> list[dict]:
    from ..services.observations import generate_observations

    return generate_observations(db, month)


@router.get("/cashflow-forecast")
def cashflow_forecast(days: int = Query(60, le=180), db: Session = Depends(get_db)) -> dict:
    from ..services.cashflow_forecast import forecast_cashflow

    return forecast_cashflow(db, days)


@router.get("/by-member")
def by_member(
    period: str | None = None,
    date_from: str | None = Query(None, alias="from"),
    date_to: str | None = Query(None, alias="to"),
    include_refunds: bool = False,
    db: Session = Depends(get_db),
) -> dict:
    """Utgifter/inkomster per hushållsmedlem + rättvis avräkning av utgifterna."""
    f, t = _range(period, date_from, date_to)
    rows = svc._analysis_rows(db, f, t, include_refunds)

    buckets: dict[str | None, dict] = {}
    for txn in rows:
        b = buckets.setdefault(
            txn.member,
            {"member": txn.member, "expenses_ore": 0, "income_ore": 0, "transaction_count": 0},
        )
        if txn.amount_ore < 0:
            b["expenses_ore"] += txn.amount_ore
        else:
            b["income_ore"] += txn.amount_ore
        b["transaction_count"] += 1

    members = sorted(
        (b for b in buckets.values() if b["member"] is not None),
        key=lambda b: b["expenses_ore"],
    )
    unassigned = buckets.get(None)

    # avräkning: om alla namngivna medlemmar delar utgifterna lika, vem ligger ute?
    settlement = []
    if len(members) >= 2:
        total_paid = sum(-b["expenses_ore"] for b in members)
        fair_share = total_paid / len(members)
        settlement = [
            {
                "member": b["member"],
                "paid_ore": -b["expenses_ore"],
                "fair_share_ore": round(fair_share),
                "diff_ore": round(-b["expenses_ore"] - fair_share),
            }
            for b in members
        ]
    return {
        "from": f,
        "to": t,
        "members": members,
        "unassigned": unassigned,
        "settlement": settlement,
    }
