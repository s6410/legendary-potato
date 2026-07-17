#!/usr/bin/env python3
"""Starta Kassaboken: bygger frontend vid behov, startar servern, öppnar webbläsaren.

    python run.py            # normal start
    python run.py --dev      # backend utan frontend (kör `npm run dev` separat)
    python run.py --no-open  # öppna inte webbläsaren automatiskt
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FRONTEND = ROOT / "frontend"
DIST = FRONTEND / "dist"
HOST, PORT = "127.0.0.1", 8014


def ensure_frontend_built() -> None:
    if DIST.joinpath("index.html").is_file():
        return
    print("Frontend är inte byggd — bygger nu (kräver Node.js, engångsjobb)...")
    npm = "npm.cmd" if sys.platform == "win32" else "npm"
    subprocess.run([npm, "ci"], cwd=FRONTEND, check=True)
    subprocess.run([npm, "run", "build"], cwd=FRONTEND, check=True)


def open_when_ready(url: str) -> None:
    for _ in range(60):
        try:
            with urllib.request.urlopen(f"{url}/api/health", timeout=1):
                webbrowser.open(url)
                return
        except OSError:
            time.sleep(0.5)


def main() -> None:
    parser = argparse.ArgumentParser(description="Starta Kassaboken")
    parser.add_argument("--dev", action="store_true", help="backend-läge utan byggd frontend")
    parser.add_argument("--no-open", action="store_true", help="öppna inte webbläsaren")
    parser.add_argument("--port", type=int, default=PORT)
    args = parser.parse_args()

    sys.path.insert(0, str(ROOT / "backend"))
    if not args.dev:
        ensure_frontend_built()

    import uvicorn

    from app.main import create_app

    app = create_app(serve_frontend=not args.dev)
    url = f"http://{HOST}:{args.port}"
    print(f"Kassaboken körs på {url}")
    if args.dev:
        print("Dev-läge: starta frontend med `cd frontend && npm run dev`")
    if not args.no_open and not args.dev:
        threading.Thread(target=open_when_ready, args=(url,), daemon=True).start()
    uvicorn.run(app, host=HOST, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
