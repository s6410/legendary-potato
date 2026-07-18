"""Delade kategorihjälpare."""
from __future__ import annotations


def category_path(cats: dict, category_id: int | None) -> str | None:
    """'Huvudkategori › Underkategori' (eller bara namnet för toppnivå)."""
    if category_id is None or category_id not in cats:
        return None
    cat = cats[category_id]
    if cat.parent_id and cat.parent_id in cats:
        return f"{cats[cat.parent_id].name} › {cat.name}"
    return cat.name
