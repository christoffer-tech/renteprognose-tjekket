"""Jyske Realkredits "Resultat af rentetilpasning"-notater.

Efter hver refinansieringsauktion (1. januar, 1. april, 1. juli, 1. oktober)
udsender Jyske Realkredit en opgoerelse over de renter kunderne faktisk fik:

    Resultat af rentetilpasning pr. 1. januar 2022

                          Med afdrag                        Uden afdrag
         Kontantlånsrente  Brutto  Netto    Kontantlånsrente  Brutto  Netto
    F1        -0,22%       3.302   3.191        -0,22%         926    736
    F3        -0,22%       3.517   3.369        -0,22%       1.072    844
    F5         0,03%       3.518   3.344         0,04%         999    743

Det er **facit** for de prognoser soster-notatet "Forventning til
rentetilpasning" stillede (se `banks/jyske_anbefaling.py`), og vaerdierne
dateres derfor paa selve refinansieringsdatoen. Den foerste kolonne ("med
afdrag") bruges - samme valg som notatet selv fremhaever.

Krydstjek: notatet pr. 1. januar 2022 oplyser F1 = -0,22 %, praecis samme
vaerdi som grafen i prognosenotatet fra september 2022 viser som realiseret
("F1: 2022"), og som den eksterne facit-serie dermed allerede havde.
"""
from __future__ import annotations

import calendar
import re

BANK_ID = "jyske"

TITLE_RE = re.compile(
    r"Resultat\s+af\s+rentetilpasning\s+pr\.?\s*1\.?\s*([a-zæøå]+)\s+(\d{4})",
    re.IGNORECASE)
MONTHS = {"januar": 1, "februar": 2, "marts": 3, "april": 4, "maj": 5,
          "juni": 6, "juli": 7, "august": 8, "september": 9, "oktober": 10,
          "november": 11, "december": 12}
# '    F1        -0,22%       3.302   3.191 ...' - foerste procent er 'med afdrag'.
# Bindestegen maa ikke indgaa i mellemrummet foer tallet, for minus er en del af
# vaerdien ('-0,22'), ikke en separator.
ROW_RE = re.compile(r"^\s*F\s*([1-6])\b[^\d%+\-]*(-?\d+,\d+)\s*%")
# Produkterne i projektet. F2/F4/F6 har ikke en prognose at maale imod.
PRODUCT = {"1": "f1", "3": "f3", "5": "f5"}


def _num(text: str) -> float:
    return round(float(text.replace(".", "").replace(",", ".")), 3)


def parse_text(text: str) -> dict | None:
    """Returnerer {'date': '2022-01-01', 'rates': {'f1': -0.22, ...}}."""
    m = TITLE_RE.search(text)
    if not m:
        return None
    month = MONTHS.get(m.group(1).lower())
    if month is None:
        return None
    date = f"{int(m.group(2))}-{month:02d}-01"

    rates: dict[str, float] = {}
    for line in text.splitlines():
        row = ROW_RE.match(line)
        if not row:
            continue
        prod = PRODUCT.get(row.group(1))
        if prod and prod not in rates:
            rates[prod] = _num(row.group(2))
    if not rates:
        return None
    return {"date": date, "rates": rates, "edition": _edition(text)}


def _edition(text: str) -> str | None:
    """'BOLIGØKONOMI | November 2021' - notatets udgivelsesmaaned."""
    m = re.search(r"BOLIG[ØO]KONOMI\s*\|\s*([A-Za-zÆØÅæøå]+)\s+(\d{4})",
                  text, re.IGNORECASE)
    if not m:
        return None
    month = MONTHS.get(m.group(1).lower())
    if month is None:
        return None
    year = int(m.group(2))
    return f"{year}-{month:02d}-{calendar.monthrange(year, month)[1]:02d}"


def parse_pdf_bytes(pdf_bytes: bytes) -> dict | None:
    from banks.jyske_renteprognose import _text_via_pdftotext

    text = _text_via_pdftotext(pdf_bytes)
    return parse_text(text) if text else None
