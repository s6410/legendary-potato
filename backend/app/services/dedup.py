"""Dubblettdetektering med förekomstindex.

Naturlig nyckel: (konto, datum, belopp, normaliserad rådbeskrivning). Två
identiska köp samma dag får occurrence_index 0 och 1 — räknat per nyckel, inte
per radposition — så överlappande exporter reproducerar samma hash oavsett
radordning i filen.
"""
from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import Transaction
from .parsing import ParsedRow

SEP = "\x1f"


@dataclass
class HashedRow:
    row: ParsedRow
    occurrence_index: int
    dedup_hash: str
    is_duplicate: bool = False


def _key(row: ParsedRow) -> tuple:
    return (row.booked_date, row.amount_ore, row.description_raw.strip().casefold())


def compute_hash(account_id: int, row: ParsedRow, occurrence_index: int) -> str:
    payload = SEP.join(
        [
            str(account_id),
            row.booked_date,
            str(row.amount_ore),
            row.description_raw.strip().casefold(),
            str(occurrence_index),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def assign_hashes(account_id: int, rows: list[ParsedRow]) -> list[HashedRow]:
    counters: dict[tuple, int] = defaultdict(int)
    out: list[HashedRow] = []
    for row in rows:
        k = _key(row)
        idx = counters[k]
        counters[k] += 1
        out.append(HashedRow(row=row, occurrence_index=idx, dedup_hash=compute_hash(account_id, row, idx)))
    return out


def mark_duplicates(db: Session, account_id: int, hashed: list[HashedRow]) -> None:
    if not hashed:
        return
    hashes = [h.dedup_hash for h in hashed]
    existing: set[str] = set()
    for chunk_start in range(0, len(hashes), 500):
        chunk = hashes[chunk_start : chunk_start + 500]
        existing.update(
            db.scalars(
                select(Transaction.dedup_hash).where(
                    Transaction.account_id == account_id,
                    Transaction.dedup_hash.in_(chunk),
                )
            )
        )
    for h in hashed:
        h.is_duplicate = h.dedup_hash in existing
