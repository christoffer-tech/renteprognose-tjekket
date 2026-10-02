"""Jyske Bank-parser: jyskebank.dk/bolig/anbefalinger-og-forventninger

Tre tabeller ('Lånerente pr.' som rækker):
- Jyske Rentetilpasning F1/F3/F5 (transponeret layout)
- Jyske Frihed variabel basisrente
- Jyske Fast Rente 30 år (flad kupon, ikke en reel prognose -> 'fast30kupon')

F-renterne er EKSKL. kursfradrag (jf. fodnote). Justering (+0,3 F1 / +0,2 F3/F5)
sker i sammenligningen (compare.py), så rådata forbliver urørte.
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup

from common import (clean, obs_date_for, parse_dk_date, parse_rate,
                    table_rows)

BANK_ID = "jyske"
LABEL = "Jyske Bank"
PAGE_URL = "https://www.jyskebank.dk/bolig/anbefalinger-og-forventninger"

# kursfradrag der lægges til ved sammenligning mod kontantlånsrenter inkl. fradrag
KURSFRADRAG = {"f1": 0.3, "f3": 0.2, "f5": 0.2}


def parse_snapshot(html: str, source: str, capture_ts: str | None,
                   fallback_date: str) -> dict | None:
    soup = BeautifulSoup(html, "lxml")
    txt = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
    pub_date = None
    m = re.search(r"[Oo]pdateret\s+(\d{1,2}[.-]\d{1,2}[.-]\d{2,4})", txt)
    if m:
        pub_date = parse_dk_date(m.group(1))
    if pub_date is None:
        pub_date = fallback_date

    data_rows: dict[str, dict] = {}
    raw_rows: dict[str, list] = {}
    targets_seen: list = []

    for t in soup.find_all("table"):
        rows = table_rows(t)
        if not rows:
            continue
        hdr = [c.lower() for c in rows[0]]
        if not any("lånerente" in c for c in hdr):
            continue
        # klassificér tabel ud fra kolonneoverskrifter
        is_f = any(re.search(r"\bf[135]\b", c) for c in hdr[1:])
        is_frihed = any("frihed" in c for c in hdr)
        is_fast = any("fast rente" in c for c in hdr)
        if not (is_f or is_frihed or is_fast):
            continue

        date_rows: list[tuple[str, list]] = []
        for r in rows[1:]:
            if not r:
                continue
            d = parse_dk_date(r[0])
            if not d:
                continue
            date_rows.append((d, [parse_rate(c) for c in r[1:]]))
        if len(date_rows) < 2:
            continue

        if targets_seen and [d for d, _ in date_rows[1:]] != targets_seen:
            print(f"    ADVARSEL: afvigende måldatoer i Jyske-tabel {rows[0]}",
                  flush=True)
        targets_seen = [d for d, _ in date_rows[1:]]

        aktuelt_vals = date_rows[0][1]
        for j, h in enumerate(rows[0][1:]):
            hl = h.lower()
            if re.search(r"\bf1\b", hl):
                key = "f1"
            elif re.search(r"\bf3\b", hl):
                key = "f3"
            elif re.search(r"\bf5\b", hl):
                key = "f5"
            elif "frihed" in hl:
                key = "frihed"
            elif "fast rente" in hl:
                key = "fast30kupon"
            else:
                continue
            forecasts = [vals[j] if j < len(vals) else None
                         for _, vals in date_rows[1:]]
            aktuelt = aktuelt_vals[j] if j < len(aktuelt_vals) else None
            if aktuelt is None and all(f is None for f in forecasts):
                continue
            raw_rows[f"{key} ({h})"] = [aktuelt] + forecasts
            if key in data_rows:
                continue
            data_rows[key] = {"name": h, "aktuelt": aktuelt, "forecasts": forecasts}

    if not data_rows:
        return None

    return {
        "bank": BANK_ID,
        "source": source,
        "capture": capture_ts,
        "obs_date": obs_date_for(source, capture_ts, fallback_date),
        "pub_date": pub_date,
        "recalc_date": None,
        "targets": targets_seen,
        "rows": data_rows,
        "raw_rows": raw_rows,
    }
