"""Sydbank renteforventnings-PDF'er (markets.sydbank.dk).

Samme tal som HTML-tabellen paa sydbank.dk, men maanedlige udgaver der
gaar laengere tilbage (verificeret sep 2022 - maj 2025 + aktuel). Format:
'Renteforventninger for Danmark pr. <dato>' med kolonnerne P.t. | 3 mdr. |
6 mdr. | 12 mdr. Tallene i parentes er forrige udgave og ignoreres.

Bemaerk: '3-aars realkreditrente' er her en 3-aarig rente (= f3), modsat
den gamle HTML-side (2007-2019) hvor den korte 3-aars rente mappes til
fkort. Derfor egen canonical-mapping her.
"""
from __future__ import annotations

import io
import re

import pdfplumber

from common import add_months, clean, obs_date_for, parse_dk_date

BANK_ID = "sydbank"

# Verificerede udgaver (ID paa markets.sydbank.dk). Listen kan udvides -
# nye udgaver findes via soegning paa "markets.sydbank.dk renteforventninger".
PDF_IDS = [
    "0041177-098191",  # 1. september 2022
    "0041177-101710",  # 1. marts 2023
    "0043215-102264",  # 29. marts 2023
    "0045527-103390",  # 1. juni 2023
    "0043215-107218",  # 4. januar 2024
    "0044685-108677",  # 21. marts 2024
    "0044685-111557",  # 5. september 2024
    "0038242-112785",  # 8. november 2024
    "0038242-113177",  # 2. december 2024
    "0038242-115934",  # 6. maj 2025
    "0038242-125086",  # aktuel (2026)
]

PDF_URL = ("https://markets.sydbank.dk/PublicationsWebHandler/Default.aspx"
           "?ID={id}")

HORIZONS = [3, 6, 12]

# (moenster i raekkelabel, kanonisk noegle)
PRODUCTS = [
    (r"3[\s-]*m[åaæ]neders rente\s*\(cibor\)", "cibor3"),
    (r"10[\s-]*[aå]rig statsobligationsrente", "stat10"),
    (r"f[\s-]*kort realkreditrente", "fkort"),
    (r"3[\s-]*[aå]rs realkreditrente", "f3"),
    (r"5[\s-]*[aå]rs realkreditrente", "f5"),
    (r"20[\s-]*[aå]rs realkreditrente", "fast20"),
    (r"30[\s-]*[aå]rs realkreditrente", "fast30"),
]


def _num(text: str) -> float | None:
    text = text.replace(".", "").replace(",", ".")
    try:
        return round(float(text), 3)
    except ValueError:
        return None


def pdf_text(pdf_bytes: bytes) -> str:
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        return "\n".join((pg.extract_text() or "") for pg in pdf.pages)


def parse_pdf_text(text: str, source: str, capture_ts: str | None,
                   fallback_date: str) -> dict | None:
    """Parser til 'Renteforventninger for Danmark'-PDF'ens Danmarkstabel."""
    low = text.lower()
    # Danmarkstabellen kendes paa P.t.-kolonnen + F-kort-raekken (selve
    # overskriften er i nogle udgaver grafik og kommer ikke med i teksten)
    if "p.t." not in low or "f-kort realkreditrente" not in low:
        return None
    m = re.search(r"renteforventninger for danmark\s+pr\.\s+"
                  r"(\d{1,2}\.\s*[a-zæøå]+\s*\d{4})", text, re.IGNORECASE)
    if m:
        pub_date = parse_dk_date(m.group(1))
    else:
        # sidehovedet paa side 1 ("5. september 2024 ..."): foerste dato
        m2 = re.search(r"(\d{1,2}\.\s*[a-zæøå]+\s*\d{4})", text[:800],
                       re.IGNORECASE)
        pub_date = parse_dk_date(m2.group(1)) if m2 else None
    if pub_date is None:
        pub_date = fallback_date

    # fjern parentes-tal (forrige udgave) - ellers forskydes kolonnerne.
    # NB: kun parenteser med %-tal; tekst-parenteser som (CIBOR) beholdes.
    notext = re.sub(r"\(\s*-?[\d.,]+\s*%[^)]*\)", " ", text)
    data_rows: dict[str, dict] = {}
    raw_rows: dict[str, list] = {}
    for pattern, key in PRODUCTS:
        # label + mindst 4 rentetal i raekkefoelge (P.t., 3, 6, 12 mdr.)
        rx = re.compile(pattern + r"\s*([^\n]*?(\d+[.,]\d+\s*%[^\n]*){4})",
                        re.IGNORECASE)
        mm = rx.search(notext)
        if not mm:
            continue
        vals = re.findall(r"(-?\d+[.,]\d+)\s*%", mm.group(0))
        if len(vals) < 4:
            continue
        nums = [_num(v) for v in vals[:4]]
        if any(v is None for v in nums):
            continue
        aktuelt, fcs = nums[0], nums[1:4]
        label = clean(re.split(r"\d+[.,]\d+\s*%", mm.group(0), maxsplit=1)[0])
        raw_rows[label or key] = [aktuelt] + fcs
        if key in data_rows:
            continue
        data_rows[key] = {"name": label or key, "aktuelt": aktuelt,
                          "forecasts": fcs}

    if not data_rows:
        return None

    targets = [add_months(pub_date, h) for h in HORIZONS]
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


def parse_pdf(pdf_bytes: bytes, source: str, capture_ts: str | None,
              fallback_date: str) -> dict | None:
    try:
        return parse_pdf_text(pdf_text(pdf_bytes), source, capture_ts,
                              fallback_date)
    except Exception:
        return None


def latest_pdf_url(renter_html: str) -> str | None:
    """Find 'Grundlag for renteforventninger'-PDF-linket paa rentesiden."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(renter_html, "lxml")
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "PublicationsWebHandler" in href and "ID=" in href:
            if href.startswith("/"):
                href = "https://markets.sydbank.dk" + href
            return href
    return None
