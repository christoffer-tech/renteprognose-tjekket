"""Sparekassen Kronjylland-parser:
https://www.sparkron.dk/investering/raadgivning/renteprognose

Tabel med kolonnerne 'Aktuel' | '+ 6 måneder' | '+ 12 måneder' (relative
horisonter) og rækkerne Cita3, F-kort, F1, F3, F5, Fast 30-årig.
Første kolonne er aktuel værdi (facit). Værdier står uden %-tegn
(headeren siger 'Procent').

F-kort og tilpasningsrenter er UDEN tillæg og kursfradrag (jf. fodnote),
ligesom Jyske Bank. Fejl (facit - prognose) er upåvirkede, da både
prognose og facit bruger samme definition.
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup

from common import (add_months, clean, obs_date_for, parse_dk_date,
                    parse_rate, table_rows)

BANK_ID = "sparkron"
LABEL = "Sparekassen Kronjylland"
PAGE_URL = "https://www.sparkron.dk/investering/raadgivning/renteprognose"
# Spejlsider med samme prognosetabel (/da/, lommepenge, kron).
ALT_URLS = ["https://www.sparkron.dk/da/investering/raadgivning/renteprognose",
            "https://lommepenge.sparkron.dk/investering/raadgivning/renteprognose",
            "https://kron.sparkron.dk/investering/raadgivning/renteprognose"]

# relative horisonter (mdr.) for +6 / +12-kolonnerne
HORIZONS = [6, 12]


def canonical_product(name: str) -> str | None:
    n = name.lower()
    if re.match(r"cita\s*3\b", n):
        return "cita3"
    if re.match(r"f[-\s]?kort\b", n):
        return "fkort"
    if re.match(r"f\s?1\b", n):
        return "f1"
    if re.match(r"f\s?3\b", n):
        return "f3"
    if re.match(r"f\s?5\b", n):
        return "f5"
    if "fast" in n and "30" in n:
        return "fast30"
    return None


def rate(text: str) -> float | None:
    return parse_rate(text if "%" in text else text + " %")


def parse_snapshot(html: str, source: str, capture_ts: str | None,
                   fallback_date: str) -> dict | None:
    soup = BeautifulSoup(html, "lxml")
    txt = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))

    pub_date = None
    m = re.search(r"Aktuel\s+(\d{1,2}\.\s*[a-zæøå]+\s*\d{4})", txt)
    if m:
        pub_date = parse_dk_date(m.group(1))
    if pub_date is None:
        m = re.search(r"(\d{1,2}\.\s*[a-zæøå]+\s*\d{4})", txt)
        if m:
            pub_date = parse_dk_date(m.group(1))
    if pub_date is None:
        pub_date = fallback_date

    table = None
    for t in soup.find_all("table"):
        cells = [clean(c.get_text(" ", strip=True)).lower()
                 for c in t.find_all(["td", "th"])]
        joined = " ".join(cells)
        if "aktuel" in joined and "12 m" in joined.replace("å", "a"):
            table = t
            break
    if table is None:
        # fallback: tabel med Cita3/F-kort-rækker
        for t in soup.find_all("table"):
            cells = [clean(c.get_text(" ", strip=True)).lower()
                     for c in t.find_all(["td", "th"])]
            if sum(canonical_product(c) is not None for c in cells) >= 3:
                table = t
                break
    if table is None:
        return None

    rows = table_rows(table)
    header_idx = next((i for i, r in enumerate(rows)
                       if any("aktuel" in c.lower() for c in r)), None)
    data_start = (header_idx + 1) if header_idx is not None else 0

    # horisonter læses fra headeren ('+ 6 måneder' / '+3m' / ...); ellers default
    offsets = list(HORIZONS)
    if header_idx is not None:
        found = []
        for c in rows[header_idx][1:]:
            m = re.search(r"\+\s*(\d+)\s*m", c.lower())
            if m:
                found.append(int(m.group(1)))
        if found:
            offsets = found

    data_rows: dict[str, dict] = {}
    raw_rows: dict[str, list] = {}
    for r in rows[data_start:]:
        if not r:
            continue
        key = canonical_product(clean(r[0]))
        if key is None:
            continue
        vals = [rate(c) for c in r[1:]]
        vals = [v for v in vals if v is not None]
        if len(vals) < len(offsets) + 1:
            continue
        aktuelt, fcs = vals[0], vals[1:len(offsets) + 1]
        name = clean(r[0])
        raw_rows[name] = [aktuelt] + fcs
        if key in data_rows:
            continue
        data_rows[key] = {"name": name, "aktuelt": aktuelt, "forecasts": fcs}

    if not data_rows:
        return None

    targets = [add_months(pub_date, h) for h in offsets]
    return {
        "bank": BANK_ID,
        "source": source,
        "capture": capture_ts,
        "obs_date": obs_date_for(source, capture_ts, fallback_date),
        "pub_date": pub_date,
        "recalc_date": None,
        "targets": targets,
        "rows": data_rows,
        "raw_rows": raw_rows,
    }
