"""Normalisering av transaktionsbeskrivningar till `description_norm`.

Målet är att "KORTKÖP 250114 ICA SUPERMARKET SÖDER" och
"Kortköp 250619 ICA SUPERMARKET SÖDER" båda blir "ica supermarket söder",
så att regler, kvittningsmatchning och prenumerationsdetektering fungerar.
"""
from __future__ import annotations

import re

_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^(kortköp|korttransaktion|reservation|autogiro|betalning|swish (?:inbetalning|betalning))\s+", re.I),
    re.compile(r"^\d{6}\s+"),                      # datumprefix kvar efter "kortköp "
    re.compile(r"/\d{2}[-./]\d{2}[-./]\d{2}$"),    # SEB-stil köpdatum-suffix "/26-06-28"
    re.compile(r"\b\d{5,}\b"),                     # långa sifferserier (kortnr, referenser)
    re.compile(r"\s+\d{2}[-./]\d{2}[-./]\d{2,4}$"),  # avslutande datum
]

_WS = re.compile(r"\s+")


def normalize_description(raw: str) -> str:
    s = raw.strip().casefold()
    s = s.replace("\xa0", " ")
    for pat in _PATTERNS:
        s = pat.sub(" ", s)
    s = _WS.sub(" ", s).strip(" ,.-")
    return s[:60] if s else raw.strip().casefold()[:60]
