"""Sydbank refinansierings-artikler (sydbank.dk/aktuelt/refinansiering m.fl.).

Evergreen-URL der overskrives hvert kvartal ('Ny rente paa dit laan fra
<maaned aar>'): 'F1 ...: ca. 3,1 %' for naeste refinansiering. Historik via
Wayback-captures af samme URL. Samme F1/F3/F5-definition som hovedtabellen.
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup

from common import clean, obs_date_for, parse_dk_date, parse_rate

BANK_ID = "sydbank"

PAGE_URL = "https://www.sydbank.dk/aktuelt/refinansiering"


def parse_article(html: str, source: str, capture_ts: str | None,
                  fallback_date: str) -> dict | None:
    soup = BeautifulSoup(html, "lxml")
    txt = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))

    pub_date = None
    # 'Bolig | 4. sep. 2026 | 3 MIN.' eller '4. september 2026'
    m = re.search(r"(\d{1,2}\.\s*[a-zæøå]+\.?\s*20\d{2})", txt, re.IGNORECASE)
    if m:
        pub_date = parse_dk_date(m.group(1))
    if pub_date is None:
        pub_date = fallback_date

    # maaldato: 'fra januar 2027' i overskriften
    target = None
    m = re.search(r"fra\s+(januar|februar|marts|april|maj|juni|juli|august|"
                  r"september|oktober|november|december)\s+(20\d{2})",
                  txt, re.IGNORECASE)
    if m:
        target = parse_dk_date(f"1. {m.group(1)} {m.group(2)}")
    if target is None:
        return None

    rows: dict[str, dict] = {}
    raw_rows: dict[str, list] = {}
    names = {"f1": "F1 realkreditrente", "f3": "F3 realkreditrente",
             "f5": "F5 realkreditrente"}
    for key in ("f1", "f3", "f5"):
        # 'F1 (fast rente i 1 år): ca. 3,1 %'
        rx = re.compile(re.escape(key.upper()) + r".{0,60}?ca\.\s*"
                        r"(-?[\d,.\s]+)\s*%", re.IGNORECASE)
        mm = rx.search(txt)
        if not mm:
            continue
        fc = parse_rate(mm.group(1) + " %")
        if fc is None:
            continue
        rows[key] = {"name": names[key], "aktuelt": None, "forecasts": [fc],
                     "targets": [target]}
        raw_rows[names[key]] = [None, fc]

    if not rows:
        return None
    return {
        "bank": BANK_ID,
        "source": source,
        "capture": capture_ts,
        "obs_date": obs_date_for(source, capture_ts, fallback_date),
        "pub_date": pub_date,
        "recalc_date": None,
        "targets": [target],
        "rows": rows,
        "raw_rows": raw_rows,
    }
