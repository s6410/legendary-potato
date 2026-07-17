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
