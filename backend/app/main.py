"""FastAPI-app för Kassaboken. `create_app()` används av både run.py och tester."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .db.engine import create_session_factory

FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


def create_app(db_path: str | None = None, serve_frontend: bool = True) -> FastAPI:
    app = FastAPI(title="Kassaboken", docs_url="/api/docs", openapi_url="/api/openapi.json")
    app.state.session_factory = create_session_factory(db_path)

    from .routers import (
        accounts,
        budgets,
        categories,
        importing,
        insights,
        links,
        reports,
        rules,
        savings,
        settings,
        transactions,
    )

    for router in (
        accounts.router,
        categories.router,
        importing.router,
        transactions.router,
        rules.router,
        links.router,
        insights.router,
        budgets.router,
        savings.router,
        reports.router,
        settings.router,
    ):
        app.include_router(router, prefix="/api")

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok", "app": "kassaboken"}

    if serve_frontend and FRONTEND_DIST.is_dir():
        app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

        dist_root = FRONTEND_DIST.resolve()

        @app.get("/{path:path}", include_in_schema=False)
        def spa_fallback(path: str) -> FileResponse:
            candidate = (FRONTEND_DIST / path).resolve()
            # containment-koll: '..'-segment får inte läsa filer utanför dist/
            if path and candidate.is_file() and candidate.is_relative_to(dist_root):
                return FileResponse(candidate)
            return FileResponse(FRONTEND_DIST / "index.html")

    return app
