"""Sydbanks "Økonomisk Oversigt" (PDF) — renteprognose pr. år.

Den månedlige makroanalyse indeholder en blok:

    Renteniveau i procent, ultimo perioden3
                                      2019          2020                2021
    10-årig stat                     -0,14     -0,30 (-0,25)       -0,20 (-0,10)
    Indskudsbevisrenten              -0,75     -0,60 (-0,85)       -0,60 (-0,85)
    3 måneders Cibor                 -0,39     -0,35 (-0,40)       -0,25 (-0,20)
    30-årig realkreditrente            1,42      1,20 (1,10)         1,30 (1,25)

Foerste kolonne er den seneste realiserede ultimoværdi (facit), de to naeste er
prognoser for kommende år ved udgangen af året. Tallet i parentes er skønnet fra
*forrige* prognose og bruges ikke.

Dette er en anden tabel end den nuværende maanedlige "Renteforventninger"-PDF
(banks/sydbank_pdf.py), som har P.t. | 3 mdr. | 6 mdr. | 12 mdr. Serien her
dækker 2020-2022, hvor der ellers ikke findes data for Sydbank, og supplerer
derfor den anden parser.
"""
from __future__ import annotations

import io
import re

import pdfplumber

from common import obs_date_for

BANK_ID = "sydbank"

# (moenster i raekkelabel, kanonisk produktnoegle)
ROW_PRODUCTS = [
    (r"^10\s*[- ]?[aå]rig\s+stat", "stat10"),
    (r"^3\s*m[åa]neders\s+cibor", "cibor3"),
    (r"^30\s*[- ]?[aå]rig\s+realkreditrente", "fast30"),
]
IGNORE_ROWS = (r"^indskudsbevis", r"^amn", r"^kilde", r"^sk[øo]n")

SECTION = "renteniveau i procent"

# "ultimo perioden" => maaldato er 31. december i prognoseaaret
TARGET_MMDD = "12-31"


def _parse_text(pdf_bytes: bytes) -> tuple[str | None, dict[str, dict]]:
    """Returner (pub_date, {produkt: {aar: (vaerdi, forrige_skoen)}})."""
    lines: list[str] = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        created = (pdf.metadata or {}).get("CreationDate") or ""
        for page in pdf.pages:
            # layout=True bevarer kolonnestrukturen i tabellen
            txt = page.extract_text(layout=True) or ""
            lines.extend(txt.splitlines())

    m = re.search(r"D:(\d{4})(\d{2})(\d{2})", str(created))
    pub = f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None

    # Find sektionen
    start = None
    for i, ln in enumerate(lines):
        if SECTION in ln.lower():
            start = i
            break
    if start is None:
        return pub, {}

    # Aarskolonnerne staar paa linjen efter sektionsoverskriften
    years: list[int] = []
    for ln in lines[start + 1:start + 4]:
        found = [int(y) for y in re.findall(r"\b(20\d{2})\b", ln)]
        if len(found) >= 2:
            years = found
            break
    if len(years) < 2:
        return pub, {}

    out: dict[str, dict] = {}
    for ln in lines[start + 1:start + 40]:
        low = re.sub(r"\s+", " ", ln).strip().lower()
        if not low or any(re.match(p, low) for p in IGNORE_ROWS):
            continue
        key = None
        for pat, k in ROW_PRODUCTS:
            if re.match(pat, low):
                key = k
                break
        if key is None:
            continue
        # Alle tal inkl. parenteser, i raekkefoelge
        tokens = re.findall(r"(-?\d+[.,]\d+)\s*(\(\s*-?\d+[.,]\d+\s*\))?", ln)
        vals = []
        for v, prev in tokens:
            vals.append((float(v.replace(",", ".")),
                         float(prev.strip("() ").replace(",", ".")) if prev else None))
        # Foerste vaerdi er den realiserede ultimovaerdi, resten er prognoser.
        if len(vals) < len(years):
            continue
        out[key] = {str(y): vals[i] for i, y in enumerate(years) if i < len(vals)}
    return pub, out


def parse_pdf(pdf_bytes: bytes, source: str, capture_ts: str | None,
              fallback_date: str) -> dict | None:
    pub, table = _parse_text(pdf_bytes)
    if not table or pub is None:
        return None

    # Maal-aar er alle aar efter det foerste (det foerste er realiseret)
    year_keys = sorted({y for row in table.values() for y in row})
    if len(year_keys) < 2:
        return None
    actual_year = year_keys[0]
    target_years = year_keys[1:]

    data_rows: dict[str, dict] = {}
    for key, row in table.items():
        if actual_year not in row:
            continue
        forecasts = [row.get(y, (None, None))[0] for y in target_years]
        if all(f is None for f in forecasts):
            continue
        data_rows[key] = {
            "name": key,
            "aktuelt": row[actual_year][0],
            "forecasts": forecasts,
        }

    if not data_rows:
        return None

    return {
        "bank": BANK_ID,
        "source": source,
        "capture": capture_ts,
        "obs_date": obs_date_for(source, capture_ts, fallback_date),
        "pub_date": pub,
        "recalc_date": None,
        "targets": [f"{y}-{TARGET_MMDD}" for y in target_years],
        "rows": data_rows,
        "raw_rows": {k: [v["aktuelt"]] + v["forecasts"]
                     for k, v in data_rows.items()},
        "actual_year": actual_year,
    }


def fetch_and_parse(url: str, source: str = "okonomisk-oversigt",
                    capture_ts: str | None = None,
                    fallback_date: str | None = None) -> dict | None:
    import datetime as dt

    import requests

    from common import UA
    r = requests.get(url, headers=UA, timeout=180)
    r.raise_for_status()
    if not r.content.startswith(b"%PDF"):
        return None
    return parse_pdf(r.content, source, capture_ts,
                     fallback_date or dt.date.today().isoformat())
