"""Fingeravtryck som identifierar en fils LAYOUT (inte innehåll)."""
from __future__ import annotations

import hashlib

SEP = "\x1f"


def compute_fingerprint(file_type: str, delimiter: str | None, header_cells: list[str]) -> str:
    cells = [str(h).strip().casefold() for h in header_cells]
    while cells and not cells[-1]:
        cells.pop()
    payload = SEP.join([file_type, delimiter or ""] + cells)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
