"""Databasmotor: SQLite med WAL, foreign keys och enkel migrationsrunner."""
from __future__ import annotations

import os
import re
from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def default_db_path() -> Path:
    """Databasfil i användarens datamapp (XDG/AppData/Library) — inte i repot."""
    if override := os.environ.get("KASSABOKEN_DB"):
        return Path(override)
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData/Roaming"))
    elif os.uname().sysname == "Darwin":  # pragma: no cover
        base = Path.home() / "Library/Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
    return base / "kassaboken" / "kassaboken.db"


def make_engine(db_path: Path | str | None = None):
    path = Path(db_path) if db_path else default_db_path()
    if str(path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{path}")

    @event.listens_for(engine, "connect")
    def _set_pragmas(dbapi_conn, _):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    return engine


def run_migrations(engine) -> None:
    """Applicera numrerade SQL-filer; version spåras med PRAGMA user_version."""
    files = sorted(MIGRATIONS_DIR.glob("[0-9]*.sql"))
    with engine.begin() as conn:
        current = conn.execute(text("PRAGMA user_version")).scalar() or 0
        for f in files:
            version = int(re.match(r"(\d+)", f.name).group(1))
            if version <= current:
                continue
            for stmt in _split_statements(f.read_text(encoding="utf-8")):
                conn.execute(text(stmt))
            conn.execute(text(f"PRAGMA user_version = {version}"))


def _split_statements(sql: str) -> list[str]:
    # Migrationsfilerna innehåller inga semikolon i strängliteraler, så en
    # enkel split räcker (kommentarsrader rensas radvis).
    lines = [ln for ln in sql.splitlines() if not ln.strip().startswith("--")]
    return [s.strip() for s in "\n".join(lines).split(";") if s.strip()]


def create_session_factory(db_path: Path | str | None = None) -> sessionmaker[Session]:
    engine = make_engine(db_path)
    run_migrations(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)
