"""Aggregat för dashboard och rapporter.

Grundregler för all statistik:
- transaktioner med is_excluded exkluderas alltid
- kategorier med kind 'transfer'/'exclude' räknas aldrig som inkomst/utgift
- båda benen i bekräftade återbetalningspar exkluderas (om inte include_refunds)
- bekräftade överföringspar exkluderas alltid
"""
from __future__ import annotations

from datetime import date, timedelta
from statistics import median

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db.models import Budget, Category, Transaction, TransactionLink


def month_range(month: str) -> tuple[str, str]:
    y, m = int(month[:4]), int(month[5:7])
    start = date(y, m, 1)
    end = date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)
    return start.isoformat(), (end - timedelta(days=1)).isoformat()


def shift_month(month: str, delta: int) -> str:
    y, m = int(month[:4]), int(month[5:7])
    total = y * 12 + (m - 1) + delta
    return f"{total // 12}-{total % 12 + 1:02d}"


def prev_month(month: str) -> str:
    return shift_month(month, -1)


def excluded_txn_ids(db: Session, include_refunds: bool = False) -> set[int]:
    ids: set[int] = set()
    for link in db.scalars(select(TransactionLink).where(TransactionLink.status == "confirmed")):
        if link.kind == "refund" and include_refunds:
            continue
        ids.add(link.txn_a_id)
        ids.add(link.txn_b_id)
    return ids


def _noise_category_ids(db: Session) -> set[int]:
    return {
        c.id
        for c in db.scalars(select(Category).where(Category.kind.in_(["transfer", "exclude"])))
    }


def _analysis_rows(
    db: Session,
    date_from: str,
    date_to: str,
    include_refunds: bool = False,
    account_id: int | None = None,
    _excluded: set[int] | None = None,
    _noise: set[int] | None = None,
) -> list[Transaction]:
    excluded = _excluded if _excluded is not None else excluded_txn_ids(db, include_refunds)
    noise = _noise if _noise is not None else _noise_category_ids(db)
    stmt = select(Transaction).where(
        Transaction.booked_date >= date_from,
        Transaction.booked_date <= date_to,
        Transaction.is_excluded == 0,
    )
    if account_id:
        stmt = stmt.where(Transaction.account_id == account_id)
    return [
        t
        for t in db.scalars(stmt)
        if t.id not in excluded and t.category_id not in noise
    ]


def _sums(rows: list[Transaction]) -> dict:
    income = sum(t.amount_ore for t in rows if t.amount_ore > 0)
    expenses = sum(t.amount_ore for t in rows if t.amount_ore < 0)
    net = income + expenses
    return {
        "income_ore": income,
        "expenses_ore": expenses,
        "net_ore": net,
        "savings_rate": round(net / income, 4) if income > 0 else None,
        "transaction_count": len(rows),
    }


def summary(db: Session, date_from: str, date_to: str, include_refunds: bool = False) -> dict:
    return _sums(_analysis_rows(db, date_from, date_to, include_refunds))


def by_category(
    db: Session,
    date_from: str,
    date_to: str,
    parent_id: int | None = None,
    include_refunds: bool = False,
) -> list[dict]:
    """Nettosummor per kategori. parent_id=None → rullas upp till huvudkategorier."""
    rows = _analysis_rows(db, date_from, date_to, include_refunds)
    cats = {c.id: c for c in db.scalars(select(Category))}

    buckets: dict[int | None, dict] = {}

    def bucket(key: int | None, name: str, color: str | None, kind: str) -> dict:
        if key not in buckets:
            buckets[key] = {
                "category_id": key, "name": name, "color": color, "kind": kind,
                "amount_ore": 0, "transaction_count": 0,
            }
        return buckets[key]

    for t in rows:
        cat = cats.get(t.category_id)
        if parent_id is None:
            if cat is None:
                b = bucket(None, "Okategoriserat", "#9ca3af", "expense")
            else:
                root = cats.get(cat.parent_id) if cat.parent_id else cat
                b = bucket(root.id, root.name, root.color, root.kind)
        else:
            if cat is None:
                continue
            if cat.parent_id == parent_id:
                b = bucket(cat.id, cat.name, cat.color or cats[parent_id].color, cat.kind)
            elif cat.id == parent_id:
                b = bucket(cat.id, f"{cat.name} (direkt)", cat.color, cat.kind)
            else:
                continue
        b["amount_ore"] += t.amount_ore
        b["transaction_count"] += 1

    out = list(buckets.values())
    out.sort(key=lambda b: b["amount_ore"])  # största utgift först
    return out


def trend(
    db: Session, months: int = 12, category_id: int | None = None,
    include_refunds: bool = False, end_month: str | None = None,
) -> list[dict]:
    newest = end_month or (
        db.scalar(select(Transaction.booked_date).order_by(Transaction.booked_date.desc()).limit(1))
        or date.today().isoformat()
    )[:7]
    cat_filter: set[int] | None = None
    if category_id is not None:
        children = set(
            db.scalars(select(Category.id).where(Category.parent_id == category_id))
        )
        cat_filter = {category_id} | children

    # beräkna exkluderingsseten en gång i stället för en gång per månad
    excluded = excluded_txn_ids(db, include_refunds)
    noise = _noise_category_ids(db)
    out = []
    for i in range(months - 1, -1, -1):
        month = shift_month(newest, -i)
        f, t = month_range(month)
        rows = _analysis_rows(db, f, t, include_refunds, _excluded=excluded, _noise=noise)
        if cat_filter is not None:
            rows = [r for r in rows if r.category_id in cat_filter]
        out.append({"month": month, **_sums(rows)})
    return out


def cashflow(db: Session, months: int = 12, include_refunds: bool = False) -> list[dict]:
    data = trend(db, months, None, include_refunds)
    cumulative = 0
    for row in data:
        cumulative += row["net_ore"]
        row["cumulative_ore"] = cumulative
    return data


def top_merchants(
    db: Session, date_from: str, date_to: str, limit: int = 10, include_refunds: bool = False
) -> list[dict]:
    rows = _analysis_rows(db, date_from, date_to, include_refunds)
    merchants: dict[str, dict] = {}
    for t in rows:
        if t.amount_ore >= 0:
            continue
        m = merchants.setdefault(
            t.description_norm,
            {"merchant": t.description_raw, "description_norm": t.description_norm,
             "amount_ore": 0, "transaction_count": 0},
        )
        m["amount_ore"] += t.amount_ore
        m["transaction_count"] += 1
    out = sorted(merchants.values(), key=lambda m: m["amount_ore"])
    return out[:limit]


def forecast(db: Session, months_ahead: int = 3, history_months: int = 6) -> dict:
    """Trimmat medel per huvudkategori över senaste hela månaderna."""
    newest = db.scalar(
        select(Transaction.booked_date).order_by(Transaction.booked_date.desc()).limit(1)
    )
    if not newest:
        return {
            "based_on_months": [],
            "months": [],
            "categories": [],
            "projected_total_monthly_ore": 0,
        }
    last_full = shift_month(newest[:7], -1)

    history: dict[int | None, list[int]] = {}
    names: dict[int | None, str] = {}
    for i in range(history_months):
        month = shift_month(last_full, -i)
        f, t = month_range(month)
        for b in by_category(db, f, t):
            if b["kind"] != "expense":
                continue
            history.setdefault(b["category_id"], []).append(b["amount_ore"])
            names[b["category_id"]] = b["name"]

    def trimmed_mean(values: list[int]) -> int:
        vals = sorted(values)
        while len(vals) < history_months:
            vals.append(0)  # månader utan utgift räknas som 0
        if len(vals) >= 4:
            vals = vals[1:-1]
        return int(sum(vals) / len(vals))

    categories = [
        {"category_id": cid, "name": names[cid], "projected_monthly_ore": trimmed_mean(vals)}
        for cid, vals in history.items()
    ]
    categories.sort(key=lambda c: c["projected_monthly_ore"])
    total = sum(c["projected_monthly_ore"] for c in categories)
    future_months = [shift_month(newest[:7], i + 1) for i in range(months_ahead)]
    return {
        "based_on_months": [shift_month(last_full, -i) for i in range(history_months - 1, -1, -1)],
        "months": future_months,
        "categories": categories,
        "projected_total_monthly_ore": total,
    }


def budget_status(db: Session, month: str, include_refunds: bool = False) -> list[dict]:
    """Aktuell budget per kategori (senaste valid_from ≤ månaden) med utfall."""
    budgets = list(db.scalars(select(Budget).where(Budget.valid_from <= month)))
    latest: dict[int, Budget] = {}
    for b in sorted(budgets, key=lambda b: b.valid_from):
        latest[b.category_id] = b
    if not latest:
        return []
    f, t = month_range(month)
    cats = {c.id: c for c in db.scalars(select(Category))}
    rows = _analysis_rows(db, f, t, include_refunds)

    spent: dict[int, int] = {cid: 0 for cid in latest}
    child_to_parent = {
        c.id: c.parent_id for c in cats.values() if c.parent_id is not None
    }
    for txn in rows:
        cid = txn.category_id
        if cid in spent:
            spent[cid] += txn.amount_ore
        parent = child_to_parent.get(cid)
        if parent in spent and cid not in latest:
            spent[parent] += txn.amount_ore

    from .categories import category_path

    out = []
    for cid, b in latest.items():
        cat = cats.get(cid)
        if not cat:
            continue
        parent = cats.get(cat.parent_id) if cat.parent_id else None
        used = -spent.get(cid, 0)
        out.append(
            {
                "budget_id": b.id,
                "category_id": cid,
                "category_path": category_path(cats, cid),
                "color": (parent or cat).color,
                "budget_ore": b.amount_ore,
                "spent_ore": used,
                "remaining_ore": b.amount_ore - used,
                "progress": round(used / b.amount_ore, 4) if b.amount_ore else None,
                "valid_from": b.valid_from,
            }
        )
    out.sort(key=lambda x: -(x["progress"] or 0))
    return out
