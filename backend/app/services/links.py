"""Kvittnings-/återbetalningsmatchning och interna överföringar.

Återbetalningar: exakt motsatt belopp, samma konto, ≤45 dagar isär.
score = 0.55·handlarlikhet + 0.30·närhet i tid + 0.15·bonus för större belopp.
Förslag skapas vid score ≥ 0.55 och bekräftas/avfärdas av användaren.

Överföringar: motsatt belopp mellan OLIKA konton inom 4 dagar.
"""
from __future__ import annotations

from datetime import date
from itertools import combinations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import Category, Transaction, TransactionLink

REFUND_WINDOW_DAYS = 45
TRANSFER_WINDOW_DAYS = 4
SCORE_THRESHOLD = 0.55
LOOKBACK_DAYS = 90

_TRANSFER_HINTS = ("överföring", "overforing", "betalning", "insättning", "uttag", "till konto", "från konto")


def _days_between(a: str, b: str) -> int:
    return abs((date.fromisoformat(a) - date.fromisoformat(b)).days)


def merchant_similarity(a: str, b: str) -> float:
    if a == b:
        return 1.0
    if len(a) >= 5 and len(b) >= 5 and (a.startswith(b) or b.startswith(a)):
        return 0.8
    ta, tb = a.split()[:1], b.split()[:1]
    if ta and tb and ta[0] == tb[0] and len(ta[0]) >= 4:
        return 0.6
    return 0.0


def refund_score(txn_a: Transaction, txn_b: Transaction) -> float:
    sim = merchant_similarity(txn_a.description_norm, txn_b.description_norm)
    if sim == 0.0:
        return 0.0
    days = _days_between(txn_a.booked_date, txn_b.booked_date)
    recency = max(0.0, 1.0 - days / REFUND_WINDOW_DAYS)
    rarity = 0.15 if abs(txn_a.amount_ore) >= 20000 else 0.0
    return min(1.0, 0.55 * sim + 0.30 * recency + rarity)


def _linked_or_dismissed(db: Session) -> tuple[set[int], set[tuple[int, int]]]:
    """-> (txn-id:n med bekräftad/föreslagen länk, avfärdade par)"""
    taken: set[int] = set()
    dismissed: set[tuple[int, int]] = set()
    for link in db.scalars(select(TransactionLink)):
        pair = (min(link.txn_a_id, link.txn_b_id), max(link.txn_a_id, link.txn_b_id))
        if link.status == "dismissed":
            dismissed.add(pair)
        else:
            taken.add(link.txn_a_id)
            taken.add(link.txn_b_id)
    return taken, dismissed


def suggest_refunds(db: Session, account_id: int | None = None) -> int:
    """Skapa förslag på återbetalningspar och kontoöverföringar. -> antal nya förslag"""
    newest = db.scalar(select(Transaction.booked_date).order_by(Transaction.booked_date.desc()).limit(1))
    if not newest:
        return 0
    cutoff = (date.fromisoformat(newest)).toordinal() - LOOKBACK_DAYS
    cutoff_date = date.fromordinal(cutoff).isoformat()

    transfer_kind_cats = {
        c.id for c in db.scalars(select(Category).where(Category.kind.in_(["transfer", "exclude"])))
    }
    stmt = select(Transaction).where(
        Transaction.booked_date >= cutoff_date,
        Transaction.amount_ore != 0,
        Transaction.is_excluded == 0,
    )
    txns = [t for t in db.scalars(stmt) if t.category_id not in transfer_kind_cats]

    taken, dismissed = _linked_or_dismissed(db)
    candidates: list[tuple[float, str, Transaction, Transaction]] = []

    by_abs: dict[int, list[Transaction]] = {}
    for t in txns:
        by_abs.setdefault(abs(t.amount_ore), []).append(t)

    for group in by_abs.values():
        if len(group) < 2:
            continue
        for a, b in combinations(group, 2):
            if a.amount_ore != -b.amount_ore:
                continue
            pair = (min(a.id, b.id), max(a.id, b.id))
            if pair in dismissed or a.id in taken or b.id in taken:
                continue
            days = _days_between(a.booked_date, b.booked_date)
            if a.account_id == b.account_id:
                if days > REFUND_WINDOW_DAYS:
                    continue
                score = refund_score(a, b)
                if score >= SCORE_THRESHOLD:
                    candidates.append((score, "refund", a, b))
            else:
                if days > TRANSFER_WINDOW_DAYS:
                    continue
                hinty = any(
                    h in a.description_norm or h in b.description_norm for h in _TRANSFER_HINTS
                )
                sim = merchant_similarity(a.description_norm, b.description_norm)
                score = 0.5 + (0.3 if hinty else 0.0) + 0.2 * sim - 0.05 * days
                if score >= SCORE_THRESHOLD:
                    candidates.append((score, "transfer", a, b))

    candidates.sort(key=lambda c: -c[0])
    claimed: set[int] = set(taken)
    created = 0
    for score, kind, a, b in candidates:
        if a.id in claimed or b.id in claimed:
            continue
        claimed.add(a.id)
        claimed.add(b.id)
        db.add(
            TransactionLink(kind=kind, txn_a_id=a.id, txn_b_id=b.id, status="suggested", score=round(score, 3))
        )
        created += 1
    db.flush()
    return created
