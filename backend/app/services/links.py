"""Kvittnings-/återbetalningsmatchning och interna överföringar.

Fylls med scoringlogik i fas 5 — importflödet anropar suggest_refunds efter
varje commit.
"""
from __future__ import annotations

from sqlalchemy.orm import Session


def suggest_refunds(db: Session, account_id: int | None = None) -> int:
    return 0
