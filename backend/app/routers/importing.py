"""Importflödet: inspect → (profilguide) → preview → commit, samt batchhistorik."""
from __future__ import annotations

import hashlib
import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db.models import Account, Category, ImportBatch, ImportFormatProfile, Transaction
from ..deps import get_db
from ..services import links as links_service
from ..services import rules as rules_service
from ..services.dedup import assign_hashes, mark_duplicates
from ..services.parsing import ParseOptions, inspect_file, parse_with_options

router = APIRouter(prefix="/import", tags=["import"])


def _profile_dict(p: ImportFormatProfile) -> dict:
    return {
        "id": p.id,
        "fingerprint": p.fingerprint,
        "name": p.name,
        "default_account_id": p.default_account_id,
        "file_type": p.file_type,
        "delimiter": p.delimiter,
        "encoding": p.encoding,
        "decimal_separator": p.decimal_separator,
        "thousands_separator": p.thousands_separator,
        "date_format": p.date_format,
        "header_row_index": p.header_row_index,
        "invert_sign": bool(p.invert_sign),
        "skip_value": p.skip_value,
        "column_mapping": json.loads(p.column_mapping),
    }


@router.post("/inspect")
async def inspect(file: UploadFile = File(...), db: Session = Depends(get_db)) -> dict:
    data = await file.read()
    try:
        insp = inspect_file(data, file.filename or "fil.csv")
    except Exception as e:  # trasig fil ska ge begripligt fel, inte 500
        raise HTTPException(422, f"Kunde inte läsa filen: {e}")
    profile = db.scalar(
        select(ImportFormatProfile).where(ImportFormatProfile.fingerprint == insp.fingerprint)
    )
    return {
        "known": profile is not None,
        "profile": _profile_dict(profile) if profile else None,
        "inspection": {
            "file_type": insp.file_type,
            "encoding": insp.encoding,
            "delimiter": insp.delimiter,
            "header_row_index": insp.header_row_index,
            "header": insp.header,
            "sample_rows": insp.sample_rows,
            "fingerprint": insp.fingerprint,
            "suggested_mapping": insp.suggested_mapping,
            "suggested_date_format": insp.suggested_date_format,
            "suggested_decimal_separator": insp.suggested_decimal_separator,
            "suggested_thousands_separator": insp.suggested_thousands_separator,
            "suggested_invert_sign": insp.suggested_invert_sign,
        },
    }


class ProfileIn(BaseModel):
    fingerprint: str
    name: str
    file_type: str
    column_mapping: dict
    default_account_id: int | None = None
    delimiter: str | None = None
    encoding: str | None = None
    decimal_separator: str = ","
    thousands_separator: str | None = None
    date_format: str = "%Y-%m-%d"
    header_row_index: int = 0
    invert_sign: bool = False
    skip_value: str | None = None


@router.get("/profiles")
def list_profiles(db: Session = Depends(get_db)) -> list[dict]:
    return [_profile_dict(p) for p in db.scalars(select(ImportFormatProfile))]


@router.post("/profiles", status_code=201)
def create_profile(body: ProfileIn, db: Session = Depends(get_db)) -> dict:
    if body.column_mapping.get("date") is None:
        raise HTTPException(422, "Mappningen måste innehålla en datumkolumn")
    if body.column_mapping.get("amount") is None and body.column_mapping.get("amount_out") is None:
        raise HTTPException(422, "Mappningen måste innehålla en beloppskolumn")
    existing = db.scalar(
        select(ImportFormatProfile).where(ImportFormatProfile.fingerprint == body.fingerprint)
    )
    payload = body.model_dump()
    payload["column_mapping"] = json.dumps(payload["column_mapping"])
    payload["invert_sign"] = int(payload["invert_sign"])
    if existing:
        for k, v in payload.items():
            setattr(existing, k, v)
        db.flush()
        return _profile_dict(existing)
    profile = ImportFormatProfile(**payload)
    db.add(profile)
    db.flush()
    return _profile_dict(profile)


@router.patch("/profiles/{profile_id}")
def update_profile(profile_id: int, body: dict, db: Session = Depends(get_db)) -> dict:
    profile = db.get(ImportFormatProfile, profile_id)
    if not profile:
        raise HTTPException(404, "Profilen finns inte")
    allowed = {
        "name", "default_account_id", "delimiter", "encoding", "decimal_separator",
        "thousands_separator", "date_format", "header_row_index", "invert_sign",
        "skip_value", "column_mapping",
    }
    for k, v in body.items():
        if k not in allowed:
            continue
        if k == "column_mapping":
            v = json.dumps(v)
        if k == "invert_sign":
            v = int(v)
        setattr(profile, k, v)
    db.flush()
    return _profile_dict(profile)


@router.delete("/profiles/{profile_id}", status_code=204)
def delete_profile(profile_id: int, db: Session = Depends(get_db)) -> None:
    profile = db.get(ImportFormatProfile, profile_id)
    if not profile:
        raise HTTPException(404, "Profilen finns inte")
    in_use = db.scalar(select(ImportBatch.id).where(ImportBatch.profile_id == profile_id).limit(1))
    if in_use:
        raise HTTPException(409, "Profilen används av importhistorik och kan inte tas bort")
    db.delete(profile)


def _prepare(db: Session, data: bytes, filename: str, profile_id: int, account_id: int | None):
    profile = db.get(ImportFormatProfile, profile_id)
    if not profile:
        raise HTTPException(404, "Profilen finns inte")
    acct_id = account_id or profile.default_account_id
    if not acct_id or not db.get(Account, acct_id):
        raise HTTPException(422, "Ange ett giltigt konto för importen")
    opts = ParseOptions.from_profile(profile)
    try:
        result = parse_with_options(data, filename, opts)
    except HTTPException:
        raise
    except Exception as e:  # trasig/oläsbar fil ska ge 422, inte 500
        raise HTTPException(422, f"Kunde inte tolka filen: {e}")
    hashed = assign_hashes(acct_id, result.rows)
    mark_duplicates(db, acct_id, hashed)
    rules = rules_service.load_rules(db)
    matched = [
        rules_service.match_rule(rules, h.row.description_norm, acct_id) for h in hashed
    ]
    return profile, acct_id, result, hashed, matched


@router.post("/preview")
async def preview(
    file: UploadFile = File(...),
    profile_id: int = Form(...),
    account_id: int | None = Form(None),
    db: Session = Depends(get_db),
) -> dict:
    data = await file.read()
    profile, acct_id, result, hashed, matched = _prepare(
        db, data, file.filename or "fil", profile_id, account_id
    )
    cat_names = {c.id: c.name for c in db.scalars(select(Category))}
    already = db.scalar(
        select(ImportBatch.id).where(
            ImportBatch.file_sha256 == hashlib.sha256(data).hexdigest(),
            ImportBatch.status == "committed",
        )
    )
    rows = [
        {
            "booked_date": h.row.booked_date,
            "amount_ore": h.row.amount_ore,
            "description": h.row.description_raw,
            "duplicate": h.is_duplicate,
            "category_id": m.category_id if m else None,
            "category_name": cat_names.get(m.category_id) if m else None,
        }
        for h, m in zip(hashed, matched)
    ]
    return {
        "account_id": acct_id,
        "profile_name": profile.name,
        "total": len(hashed),
        "new_count": sum(1 for h in hashed if not h.is_duplicate),
        "duplicate_count": sum(1 for h in hashed if h.is_duplicate),
        "auto_categorized": sum(1 for h, m in zip(hashed, matched) if m and not h.is_duplicate),
        "skipped": result.skipped,
        "identical_file_already_imported": already is not None,
        "rows": rows,
    }


@router.post("/commit", status_code=201)
async def commit(
    file: UploadFile = File(...),
    profile_id: int = Form(...),
    account_id: int | None = Form(None),
    db: Session = Depends(get_db),
) -> dict:
    data = await file.read()
    profile, acct_id, result, hashed, matched = _prepare(
        db, data, file.filename or "fil", profile_id, account_id
    )
    batch = ImportBatch(
        account_id=acct_id,
        profile_id=profile.id,
        filename=file.filename,
        file_sha256=hashlib.sha256(data).hexdigest(),
        row_count=len(hashed),
        inserted_count=sum(1 for h in hashed if not h.is_duplicate),
        duplicate_count=sum(1 for h in hashed if h.is_duplicate),
    )
    db.add(batch)
    db.flush()
    for h, m in zip(hashed, matched):
        if h.is_duplicate:
            continue
        db.add(
            Transaction(
                account_id=acct_id,
                batch_id=batch.id,
                booked_date=h.row.booked_date,
                amount_ore=h.row.amount_ore,
                description_raw=h.row.description_raw,
                description_norm=h.row.description_norm,
                balance_ore=h.row.balance_ore,
                category_id=m.category_id if m else None,
                category_source="rule" if m else None,
                applied_rule_id=m.id if m else None,
                dedup_hash=h.dedup_hash,
                occurrence_index=h.occurrence_index,
            )
        )
        if m:
            m.hit_count += 1
    try:
        db.flush()
    except IntegrityError:
        # två samtidiga commits av överlappande filer — den andra förlorar
        raise HTTPException(409, "Importen kolliderade med en annan pågående import — försök igen")
    suggested_links = links_service.suggest_refunds(db, acct_id)
    return {
        "batch_id": batch.id,
        "inserted": batch.inserted_count,
        "duplicates": batch.duplicate_count,
        "skipped": len(result.skipped),
        "suggested_links": suggested_links,
    }


@router.get("/batches")
def list_batches(db: Session = Depends(get_db)) -> list[dict]:
    accounts = {a.id: a.name for a in db.scalars(select(Account))}
    profiles = {p.id: p.name for p in db.scalars(select(ImportFormatProfile))}
    return [
        {
            "id": b.id,
            "account_id": b.account_id,
            "account_name": accounts.get(b.account_id),
            "profile_name": profiles.get(b.profile_id),
            "filename": b.filename,
            "imported_at": b.imported_at,
            "row_count": b.row_count,
            "inserted_count": b.inserted_count,
            "duplicate_count": b.duplicate_count,
            "status": b.status,
        }
        for b in db.scalars(select(ImportBatch).order_by(ImportBatch.id.desc()))
    ]


@router.post("/batches/{batch_id}/revert")
def revert_batch(batch_id: int, db: Session = Depends(get_db)) -> dict:
    batch = db.get(ImportBatch, batch_id)
    if not batch:
        raise HTTPException(404, "Batchen finns inte")
    if batch.status == "reverted":
        raise HTTPException(409, "Batchen är redan ångrad")
    txn_ids = list(
        db.scalars(select(Transaction.id).where(Transaction.batch_id == batch_id))
    )
    if txn_ids:
        from collections import Counter

        from ..db.models import CategorizationRule, TransactionLink

        # regelträffar från batchen ska inte räknas efter att raderna försvunnit
        rule_hits = Counter(
            rid
            for rid in db.scalars(
                select(Transaction.applied_rule_id).where(
                    Transaction.batch_id == batch_id,
                    Transaction.applied_rule_id.isnot(None),
                )
            )
        )
        for rule_id, hits in rule_hits.items():
            rule = db.get(CategorizationRule, rule_id)
            if rule:
                rule.hit_count = max(0, rule.hit_count - hits)

        db.query(TransactionLink).filter(
            TransactionLink.txn_a_id.in_(txn_ids) | TransactionLink.txn_b_id.in_(txn_ids)
        ).delete(synchronize_session=False)
        db.query(Transaction).filter(Transaction.batch_id == batch_id).delete(
            synchronize_session=False
        )
    batch.status = "reverted"
    return {"reverted": len(txn_ids)}
