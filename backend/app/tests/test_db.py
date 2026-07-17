from sqlalchemy import text

from app.db.engine import make_engine, run_migrations
from app.db.models import Category


def test_migrations_apply_and_are_idempotent(tmp_path):
    engine = make_engine(tmp_path / "m.db")
    run_migrations(engine)
    run_migrations(engine)  # andra körningen ska inte göra något
    with engine.connect() as conn:
        version = conn.execute(text("PRAGMA user_version")).scalar()
        assert version >= 2
        tables = {
            r[0]
            for r in conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table'")
            )
        }
    assert {
        "accounts", "categories", "transactions", "import_batches",
        "import_format_profiles", "categorization_rules", "transaction_links",
        "savings_accounts", "savings_snapshots", "target_allocations",
        "budgets", "recurring_overrides", "settings",
    } <= tables


def test_seed_categories_present(db):
    main_cats = db.query(Category).filter(Category.parent_id.is_(None)).all()
    names = {c.name for c in main_cats}
    assert {"Boende", "Mat", "Transport", "Inkomst", "Överföringar"} <= names
    subs = db.query(Category).filter(Category.parent_id.isnot(None)).count()
    assert subs > 20


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
