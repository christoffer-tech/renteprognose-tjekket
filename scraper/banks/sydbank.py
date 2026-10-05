"""Sydbank-parser: sydbank.dk/privat/produkter/boliglaan/renter

To tabeller: 'Aktuelt renteniveau' (facit) og 'Vores renteforventninger'
med relative horisonter 0-3 / 3-6 / 6-12 mdr. Ingen publiceringsdato på
siden -> pub_date = obs/fallback. Kræver browser-headers (403 ellers).
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup

from common import (BROWSER_HEADERS, add_months, clean, fetch,
                     obs_date_for, parse_dk_date, parse_rate, table_rows)

BANK_ID = "sydbank"
LABEL = "Sydbank"
PAGE_URL = "https://www.sydbank.dk/privat/produkter/boliglaan/renter"
# Ældre renteforventningsside (2007-2019).
ALT_URLS = ["https://www.sydbank.dk/privat/raadgivning/bolig/laaneanbefaling/"
            "renteforventning"]

# relativ horisont (mdr. interval-slut) pr. kolonne
HORIZONS = [3, 6, 12]


def canonical_product(name: str) -> str | None:
    n = name.lower()
    if "statsobligation" in n and "10" in n:
        return "stat10"
    if "cibor" in n and "3" in n:
        return "cibor3"
    if "cita" in n and "3" in n:
        return "cita3"
    if re.match(r"f[-\s]?kort\b", n):
        return "fkort"
    if re.search(r"\bf3\b", n):
        return "f3"
    if re.search(r"\bf5\b", n):
        return "f5"
    # gammel side (2007-2019): '3 års realkreditrente' var en KORT rente
    # (niveauer omkring nul/negative i 2015-2016, som CIBOR - ikke som
    # 3-årige renter) og mappes derfor til fkort. Det er et ANDET produkt
    # end PDF'ernes '3-års realkreditrente (januar 20XX)', som har sin egen
    # F-kort-række ved siden af og mapper til f3 (se banks/sydbank_pdf.py).
    if re.match(r"3[\s-]*(?:års|ars|aar)\s*realkreditrente", n):
        return "fkort"
    if "30" in n and "realkreditrente" in n:
        return "fast30"
    return None


def rate_cells(cells: list[str]) -> list[float]:
    """Udtræk renter fra en rækkes celler (værdier kan stå uden %-tegn)."""
    out = []
    for c in cells:
        v = parse_rate(c if "%" in c else c + " %")
        if v is not None:
            out.append(v)
    return out


def fetch_page(url: str) -> str:
    return fetch(url, headers=BROWSER_HEADERS)


def parse_snapshot(html: str, source: str, capture_ts: str | None,
                   fallback_date: str) -> dict | None:
    soup = BeautifulSoup(html, "lxml")
    txt = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))

    aktuelt: dict[str, float] = {}
    forecasts: dict[str, list] = {}
    names: dict[str, str] = {}
    horizons = list(HORIZONS)

    for t in soup.find_all("table"):
        text = t.get_text(" ", strip=True).lower()
        rows = table_rows(t)
        if not rows:
            continue
        hdr = rows[0]
        # Gammelt layout (2007-2019): '1. oktober | 0 - 3 mdr. | 3 - 6 mdr. |
        # 6 - 12 mdr.' hvor foerste kolonne er det aktuelle renteniveau.
        # Nuværende layout har samme header, men UDEN Aktuelt-kolonne
        # (Aktuelt staar i en separat tabel) - saa 3 vaerdier er nok.
        found = [int(x) for x in re.findall(r"(\d+)\s*mdr", " ".join(hdr), re.I)]
        if len(found) >= len(HORIZONS) and len(hdr) >= len(HORIZONS) + 1:
            for r in rows[1:]:
                if not r:
                    continue
                key = canonical_product(clean(r[0]))
                if key is None:
                    continue
                vals = rate_cells(r[1:])
                if len(vals) >= len(HORIZONS) + 1:
                    aktuelt[key] = vals[0]
                    forecasts[key] = vals[1:len(HORIZONS) + 1]
                    names[key] = clean(r[0])
                elif len(vals) >= len(HORIZONS):
                    forecasts[key] = vals[:len(HORIZONS)]
                    names[key] = clean(r[0])
            horizons = found[-len(HORIZONS):]
        elif "aktuelt renteniveau" in text:
            # NB: ingen header-række - første række er allerede et produkt
            for r in rows:
                if not r:
                    continue
                key = canonical_product(clean(r[0]))
                if key is None:
                    continue
                vals = rate_cells(r[1:])
                if vals:
                    aktuelt[key] = vals[0]
                    names[key] = clean(r[0])
        elif "renteforventning" in text:
            for r in rows[1:]:
                if not r:
                    continue
                key = canonical_product(clean(r[0]))
                if key is None:
                    continue
                vals = rate_cells(r[1:])
                if len(vals) >= 3:
                    forecasts[key] = vals[:3]
                    names[key] = clean(r[0])

    if not forecasts:
        return None

    pub_date = fallback_date
    m = re.search(r"renteforventning for Danmark\s+(\d{1,2}\.\s*[a-zæøå]+)", txt, re.I)
    if m:
        pub_date = parse_dk_date(f"{m.group(1)} {fallback_date[:4]}") or pub_date
    targets = [add_months(pub_date, h) for h in horizons]

    data_rows: dict[str, dict] = {}
    raw_rows: dict[str, list] = {}
    for key, fcs in forecasts.items():
        data_rows[key] = {"name": names.get(key, key),
                          "aktuelt": aktuelt.get(key),
                          "forecasts": fcs}
        raw_rows[names.get(key, key)] = [aktuelt.get(key)] + fcs

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
