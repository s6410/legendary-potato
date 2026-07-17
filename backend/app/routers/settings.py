"""Enkla nyckel/värde-inställningar."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import Setting
from ..deps import get_db

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("")
def get_settings(db: Session = Depends(get_db)) -> dict:
    return {s.key: s.value for s in db.scalars(select(Setting))}


@router.put("")
def put_settings(body: dict, db: Session = Depends(get_db)) -> dict:
    for key, value in body.items():
        setting = db.get(Setting, key)
        if setting:
            setting.value = None if value is None else str(value)
        else:
            db.add(Setting(key=key, value=None if value is None else str(value)))
    return {"ok": True}
