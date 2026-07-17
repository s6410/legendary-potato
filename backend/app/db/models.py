"""SQLAlchemy-modeller — speglar migrations/001_init.sql."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


class Base(DeclarativeBase):
    pass


class Account(Base):
    __tablename__ = "accounts"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    kind: Mapped[str] = mapped_column(default="checking")
    currency: Mapped[str] = mapped_column(default="SEK")
    is_active: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[str] = mapped_column(default=now_iso)


class Category(Base):
    __tablename__ = "categories"
    id: Mapped[int] = mapped_column(primary_key=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"))
    name: Mapped[str]
    kind: Mapped[str] = mapped_column(default="expense")
    color: Mapped[str | None]
    icon: Mapped[str | None]
    sort_order: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[str] = mapped_column(default=now_iso)


class ImportFormatProfile(Base):
    __tablename__ = "import_format_profiles"
    id: Mapped[int] = mapped_column(primary_key=True)
    fingerprint: Mapped[str] = mapped_column(unique=True)
    name: Mapped[str]
    default_account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"))
    file_type: Mapped[str]
    delimiter: Mapped[str | None]
    encoding: Mapped[str | None]
    decimal_separator: Mapped[str] = mapped_column(default=",")
    thousands_separator: Mapped[str | None]
    date_format: Mapped[str] = mapped_column(default="%Y-%m-%d")
    header_row_index: Mapped[int] = mapped_column(default=0)
    invert_sign: Mapped[int] = mapped_column(default=0)
    skip_value: Mapped[str | None]
    column_mapping: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(default=now_iso)


class ImportBatch(Base):
    __tablename__ = "import_batches"
    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    profile_id: Mapped[int] = mapped_column(ForeignKey("import_format_profiles.id"))
    filename: Mapped[str | None]
    file_sha256: Mapped[str | None]
    imported_at: Mapped[str] = mapped_column(default=now_iso)
    row_count: Mapped[int] = mapped_column(default=0)
    inserted_count: Mapped[int] = mapped_column(default=0)
    duplicate_count: Mapped[int] = mapped_column(default=0)
    status: Mapped[str] = mapped_column(default="committed")


class Transaction(Base):
    __tablename__ = "transactions"
    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    batch_id: Mapped[int] = mapped_column(ForeignKey("import_batches.id"))
    booked_date: Mapped[str]
    amount_ore: Mapped[int]
    description_raw: Mapped[str]
    description_norm: Mapped[str]
    balance_ore: Mapped[int | None]
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"))
    category_source: Mapped[str | None]
    applied_rule_id: Mapped[int | None]
    dedup_hash: Mapped[str]
    occurrence_index: Mapped[int] = mapped_column(default=0)
    is_excluded: Mapped[int] = mapped_column(default=0)
    note: Mapped[str | None]
    created_at: Mapped[str] = mapped_column(default=now_iso)


class CategorizationRule(Base):
    __tablename__ = "categorization_rules"
    id: Mapped[int] = mapped_column(primary_key=True)
    match_type: Mapped[str]
    pattern: Mapped[str]
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"))
    account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"))
    priority: Mapped[int] = mapped_column(default=0)
    hit_count: Mapped[int] = mapped_column(default=0)
    updated_at: Mapped[str] = mapped_column(default=now_iso)
    created_at: Mapped[str] = mapped_column(default=now_iso)


class TransactionLink(Base):
    __tablename__ = "transaction_links"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str]
    txn_a_id: Mapped[int] = mapped_column(ForeignKey("transactions.id"))
    txn_b_id: Mapped[int] = mapped_column(ForeignKey("transactions.id"))
    status: Mapped[str] = mapped_column(default="suggested")
    score: Mapped[float | None]
    created_at: Mapped[str] = mapped_column(default=now_iso)


class SavingsAccount(Base):
    __tablename__ = "savings_accounts"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    asset_class: Mapped[str] = mapped_column(default="other")
    is_active: Mapped[int] = mapped_column(default=1)
    sort_order: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[str] = mapped_column(default=now_iso)


class SavingsSnapshot(Base):
    __tablename__ = "savings_snapshots"
    id: Mapped[int] = mapped_column(primary_key=True)
    savings_account_id: Mapped[int] = mapped_column(ForeignKey("savings_accounts.id"))
    snapshot_date: Mapped[str]
    value_ore: Mapped[int]
    created_at: Mapped[str] = mapped_column(default=now_iso)


class TargetAllocation(Base):
    __tablename__ = "target_allocations"
    id: Mapped[int] = mapped_column(primary_key=True)
    asset_class: Mapped[str] = mapped_column(unique=True)
    target_pct: Mapped[float]


class Budget(Base):
    __tablename__ = "budgets"
    id: Mapped[int] = mapped_column(primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"))
    amount_ore: Mapped[int]
    valid_from: Mapped[str]
    created_at: Mapped[str] = mapped_column(default=now_iso)


class RecurringOverride(Base):
    __tablename__ = "recurring_overrides"
    id: Mapped[int] = mapped_column(primary_key=True)
    description_norm: Mapped[str]
    account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"))
    status: Mapped[str]


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(primary_key=True)
    value: Mapped[str | None]
