"""Nordea-parser: nordea.dk/privat/produkter/boliglaan/nordeas-renteforventninger.html

Tabel med faste kalendermål. Første datokolonne er aktuel værdi.
'kurs'-rækken springes over (kurs er ikke en rente).
CITA6/CIBOR-rækker er UDEN tillæg (jf. fodnoter) og svarer dermed til
Nykredits CITA-rækker.
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup

from common import (clean, obs_date_for, parse_dk_date, parse_rate,
                    table_rows)

BANK_ID = "nordea"
LABEL = "Nordea"
PAGE_URL = ("https://www.nordea.dk/privat/produkter/boliglaan/"
            "nordeas-renteforventninger.html")


def canonical_product(name: str) -> str | None:
    n = name.lower()
    if "kurs" in n:
        return None  # kurs-række: ikke en rente
    if "obligation" in n.replace("-", "") and ("effektiv" in n or "4" in n):
        return "fast30"
    if re.search(r"\bf1\b", n):
        return "f1"
    if re.search(r"\bf3\b", n):
        return "f3"
    if re.search(r"\bf5\b", n):
        return "f5"
    if "cita6" in n or "cita 6" in n:
        return "cita6"
    if "cibor3" in n or "cibor 3" in n:
        return "cibor3"
    if "cibor6" in n or "cibor 6" in n:
        return "cibor6"
    return "ukendt"


def parse_old_format(soup: BeautifulSoup) -> tuple | None:
    """Gammelt layout (pre-ultimo 2022): én mini-tabel pr. produkt, hvor
    første kolonne er aktuel værdi og 'Ændring'/'kurs'-rækker springes over."""
    data_rows: dict[str, dict] = {}
    raw_rows: dict[str, list] = {}
    targets: list = []
    for t in soup.find_all("table"):
        rows = table_rows(t)
        if len(rows) < 2:
            continue
        hdr_dates = [parse_dk_date(c) for c in rows[0]]
        if sum(d is not None for d in hdr_dates) < 2:
            continue
        akt_col = next(i for i, d in enumerate(hdr_dates) if d is not None)
        data_row = None
        for r in rows[1:]:
            first = r[0].lower() if r else ""
            if "ændring" in first or "kurs" in first:
                continue
            if sum(parse_rate(c) is not None for c in r) >= 2:
                data_row = r
                break
        if data_row is None:
            continue
        name = clean(data_row[0])
        key = canonical_product(name)
        if key is None or key == "ukendt":
            continue
        aktuelt = parse_rate(data_row[akt_col]) if akt_col < len(data_row) else None
        forecasts = [parse_rate(c) for c in data_row[akt_col + 1:]]
        tgts = [d for d in hdr_dates[akt_col + 1:] if d]
        if not tgts:
            continue
        if not targets:
            targets = tgts
        raw_rows[name] = [aktuelt] + forecasts
        if key in data_rows:
            continue
        data_rows[key] = {"name": name, "aktuelt": aktuelt, "forecasts": forecasts,
                          "targets": list(tgts)}
    if not data_rows:
        return None
    return targets, data_rows, raw_rows


def parse_snapshot(html: str, source: str, capture_ts: str | None,
                   fallback_date: str) -> dict | None:
    soup = BeautifulSoup(html, "lxml")
    table = None
    for t in soup.find_all("table"):
        # nyt format = én stor tabel med alle produkter (>= 5 rækker);
        # gammelt format = én mini-tabel pr. produkt (3 rækker)
        if len(table_rows(t)) < 5:
            continue
        cells = [clean(c.get_text(" ", strip=True)) for c in t.find_all(["td", "th"])]
        if sum(parse_dk_date(c) is not None for c in cells) >= 3:
            table = t
            break
    txt = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
    pub_date = None
    m = re.search(r"[Oo]pdateret\s+(\d{1,2}\.\s*[a-zæøå]+\s*\d{4})", txt)
    if m:
        pub_date = parse_dk_date(m.group(1))

    if table is None:
        old = parse_old_format(soup)
        if old is None:
            return None
        targets, data_rows, raw_rows = old
        if pub_date is None:
            pub_date = fallback_date
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

    rows = table_rows(table)
    header_idx = next((i for i, r in enumerate(rows)
                       if sum(parse_dk_date(c) is not None for c in r) >= 2), None)
    if header_idx is None:
        return None
    hdr = rows[header_idx]
    # første datokolonne = aktuel værdi
    akt_col = next(i for i, c in enumerate(hdr) if parse_dk_date(c) is not None)
    obs_ref = parse_dk_date(hdr[akt_col])
    targets = [parse_dk_date(c) for c in hdr[akt_col + 1:]]
    if not any(targets):
        return None

    data_rows: dict[str, dict] = {}
    raw_rows: dict[str, list] = {}
    for r in rows[header_idx + 1:]:
        if len(r) <= akt_col:
            continue
        name = clean(r[0])
        if not name:
            continue
        key = canonical_product(name)
        if key is None:
            continue  # kurs-række
        aktuelt = parse_rate(r[akt_col])
        forecasts = [parse_rate(c) for c in r[akt_col + 1:]]
        if aktuelt is None and all(f is None for f in forecasts):
            continue
        raw_rows[name] = [aktuelt] + forecasts
        if key == "ukendt":
            print(f"    ADVARSEL: ukendt række '{name}' - springes over", flush=True)
            continue
        if key in data_rows:
            print(f"    ADVARSEL: '{name}' kolliderer for '{key}' - beholder første",
                  flush=True)
            continue
        data_rows[key] = {"name": name, "aktuelt": aktuelt, "forecasts": forecasts}

    if not data_rows:
        return None

    if pub_date is None:
        pub_date = obs_ref or fallback_date

    return {
        "bank": BANK_ID,
        "source": source,
        "capture": capture_ts,
        "obs_date": obs_ref or obs_date_for(source, capture_ts, fallback_date),
        "pub_date": pub_date,
        "recalc_date": None,
        "targets": targets,
        "rows": data_rows,
        "raw_rows": raw_rows,
    }
