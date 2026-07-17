"""Regelmotor: matchning av description_norm mot användarens regler.

Precedens (första träff vinner):
  1. exact — kontospecifik före global
  2. prefix — längsta mönster först, kontospecifik före global
  3. contains — längsta mönster först, kontospecifik före global
  Lika: priority DESC, sedan senast uppdaterad.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import CategorizationRule, Transaction

_TYPE_ORDER = {"exact": 0, "prefix": 1, "contains": 2}


def load_rules(db: Session, account_id: int | None = None) -> list[CategorizationRule]:
    stmt = select(CategorizationRule)
    if account_id is not None:
        stmt = stmt.where(
            (CategorizationRule.account_id == account_id)
            | (CategorizationRule.account_id.is_(None))
        )
    rules = list(db.scalars(stmt))
    rules.sort(
        key=lambda r: (
            _TYPE_ORDER.get(r.match_type, 9),
            0 if r.account_id is not None else 1,   # kontospecifik före global
            -len(r.pattern),
            -r.priority,
            r.updated_at or "",
        )
    )
    return rules


def match_rule(rules: list[CategorizationRule], description_norm: str, account_id: int | None = None) -> CategorizationRule | None:
    for r in rules:
        if r.account_id is not None and account_id is not None and r.account_id != account_id:
            continue
        if r.match_type == "exact" and description_norm == r.pattern:
            return r
        if r.match_type == "prefix" and description_norm.startswith(r.pattern):
            return r
        if r.match_type == "contains" and r.pattern in description_norm:
            return r
    return None


def apply_rules_to_uncategorized(db: Session, account_id: int | None = None) -> int:
    """Kör alla regler mot okategoriserade (ej manuellt satta) transaktioner."""
    rules = load_rules(db)
    if not rules:
        return 0
    stmt = select(Transaction).where(
        Transaction.category_id.is_(None) | (Transaction.category_source == "rule")
    )
    if account_id is not None:
        stmt = stmt.where(Transaction.account_id == account_id)
    affected = 0
    for txn in db.scalars(stmt):
        rule = match_rule(rules, txn.description_norm, txn.account_id)
        new_cat = rule.category_id if rule else None
        new_rule_id = rule.id if rule else None
        if txn.category_id != new_cat or txn.applied_rule_id != new_rule_id:
            txn.category_id = new_cat
            txn.category_source = "rule" if rule else None
            txn.applied_rule_id = new_rule_id
            affected += 1
        if rule:
            rule.hit_count += 1
    return affected


def apply_single_rule(db: Session, rule: CategorizationRule) -> int:
    """Applicera EN regel på transaktioner som inte är manuellt kategoriserade
    och som saknar kategori (eller är regelsatta av samma regel)."""
    stmt = select(Transaction).where(
        (Transaction.category_source.is_(None))
        | (Transaction.category_id.is_(None))
        | (Transaction.applied_rule_id == rule.id)
    )
    if rule.account_id is not None:
        stmt = stmt.where(Transaction.account_id == rule.account_id)
    affected = 0
    for txn in db.scalars(stmt):
        if txn.category_source == "manual":
            continue
        if match_rule([rule], txn.description_norm, txn.account_id):
            if txn.category_id != rule.category_id:
                txn.category_id = rule.category_id
                txn.category_source = "rule"
                txn.applied_rule_id = rule.id
                affected += 1
    if affected:
        rule.hit_count += affected
    return affected


def suggest_prefix(description_norm: str) -> str:
    """Föreslå ett prefixmönster genom att trimma platsliknande svanstokens."""
    tokens = description_norm.split()
    if len(tokens) <= 1:
        return description_norm
    # ta bort sista token om den ser ut som ort/nummer (vanligt: "ica kvantum solna")
    if tokens[-1].isdigit() or len(tokens) >= 3:
        return " ".join(tokens[:-1])
    return description_norm
