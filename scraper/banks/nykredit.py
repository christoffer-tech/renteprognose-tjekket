"""Nykredit-parser: https://www.nykredit.dk/dit-liv/bolig/kurser/renteprognose/"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup

from common import (clean, obs_date_for, parse_dk_date, parse_rate,
                    table_rows)

BANK_ID = "nykredit"
LABEL = "Nykredit"
PAGE_URL = "https://www.nykredit.dk/dit-liv/bolig/kurser/renteprognose/"


def canonical_product(name: str) -> str | None:
    n = name.lower()
    if re.match(r"f[-\s]?kort\b", n):
        return "fkort"
    if re.match(r"cita\s*3\b", n):
        return "cita3"
    if re.match(r"cita\s*6\b", n):
        return "cita6"
    if re.match(r"f\s?1\b", n):
        return "f1"
    if re.match(r"f\s?3\b", n):
        return "f3"
    if re.match(r"f\s?5\b", n):
        return "f5"
    if re.match(r"fast\D*20\b", n):
        return "fast20"
    if re.match(r"fast\D*30\b", n):
        return "fast30"
    return None


def parse_transposed(rows: list[list[str]]) -> tuple | None:
    if not rows or len(rows) < 3:
        return None
    header = rows[0]
    offset = 1 if not header[0].strip() else 0
    names = [clean(c) for c in header[offset:]]
    keys = [canonical_product(n) for n in names]
    if sum(k is not None for k in keys) < 2:
        return None
    aktuelt_vals: list = [None] * len(names)
    date_rows: list[tuple[str, list]] = []
    for r in rows[1:]:
        vals = r[offset:]
        if not vals:
            continue
        label = clean(r[0])
        if "ktuelt" in label:
            aktuelt_vals = [parse_rate(c) for c in vals]
        elif parse_dk_date(label):
            date_rows.append((parse_dk_date(label), [parse_rate(c) for c in vals]))
    if not date_rows:
        return None
    targets = [d for d, _ in date_rows]
    data_rows: dict[str, dict] = {}
    raw_rows: dict[str, list] = {}
    for j, (name, key) in enumerate(zip(names, keys)):
        if key is None:
            continue
        if key in data_rows:
            print(f"    ADVARSEL: '{name}' kolliderer for '{key}' - beholder første",
                  flush=True)
            continue
        forecasts = [vals[j] if j < len(vals) else None for _, vals in date_rows]
        aktuelt = aktuelt_vals[j] if j < len(aktuelt_vals) else None
        if aktuelt is None and all(f is None for f in forecasts):
            continue
        raw_rows[name] = [aktuelt] + forecasts
        data_rows[key] = {"name": name, "aktuelt": aktuelt, "forecasts": forecasts}
    if not data_rows:
        return None
    return targets, data_rows, raw_rows


def parse_snapshot(html: str, source: str, capture_ts: str | None,
                   fallback_date: str) -> dict | None:
    soup = BeautifulSoup(html, "lxml")
    table = None
    for t in soup.find_all("table"):
        if "ktuelt" in t.get_text():
            table = t
            break
    if table is None:
        return None

    rows = table_rows(table)
    if not rows:
        return None

    header_idx = next((i for i, r in enumerate(rows)
                       if any("ktuelt" in c for c in r)), None)
    data_rows: dict[str, dict] = {}
    raw_rows: dict[str, list] = {}
    targets: list[str | None] = []

    if header_idx is not None and any(parse_dk_date(c) for c in rows[header_idx][1:]):
        hdr = rows[header_idx]
        akt_col = next(i for i, c in enumerate(hdr) if "ktuelt" in c)
        targets = [parse_dk_date(c) for c in hdr[akt_col + 1:]]
        for r in rows[header_idx + 1:]:
            if len(r) <= akt_col:
                continue
            name = clean(r[0])
            if not name:
                continue
            aktuelt = parse_rate(r[akt_col])
            forecasts = [parse_rate(c) for c in r[akt_col + 1:]]
            if aktuelt is None and all(f is None for f in forecasts):
                continue
            key = canonical_product(name)
            raw_rows[name] = [aktuelt] + forecasts
            if key is None:
                print(f"    ADVARSEL: ukendt række '{name}' - springes over", flush=True)
                continue
            if key in data_rows:
                print(f"    ADVARSEL: '{name}' kolliderer for '{key}' - beholder første",
                      flush=True)
                continue
            data_rows[key] = {"name": name, "aktuelt": aktuelt, "forecasts": forecasts}
    else:
        transposed = parse_transposed(rows)
        if transposed is None:
            return None
        targets, data_rows, raw_rows = transposed

    if not data_rows:
        return None

    import re as _re
    txt = _re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
    pub_date = recalc_date = None
    m = _re.search(r"er fra\s+(\d{1,2}-\d{1,2}-\d{2,4})"
                   r"(?:\s+og genberegnet den\s+(\d{1,2}-\d{1,2}-\d{2,4}))?", txt)
    if m:
        pub_date = parse_dk_date(m.group(1))
        if m.group(2):
            recalc_date = parse_dk_date(m.group(2))
    if pub_date is None:
        pub_date = fallback_date

    return {
        "bank": BANK_ID,
        "source": source,
        "capture": capture_ts,
        "obs_date": obs_date_for(source, capture_ts, fallback_date),
        "pub_date": pub_date,
        "recalc_date": recalc_date,
        "targets": targets,
        "rows": data_rows,
        "raw_rows": raw_rows,
    }
