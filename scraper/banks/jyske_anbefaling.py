"""Jyske Realkredits "Forventning til rentetilpasning"-notater (2021-2023).

Notaterne findes i to formater, og de kraever hver sin parser:

- **Tabel** (2024-): "Forventninger til realkreditrenten" med eksplicitte
  datoer. Laeses af `banks/jyske_pdf.py` (pdfplumber).
- **Graf** (2021-2023): én figur pr. produkt, hvor den forventede rente staar
  som et label over sojlen for den kommende refinansiering:

      Figur 1: F1-lån ved april rentetilpasning 2020 og forventning til 2021

                            F1: 2020                           F1: 2021*
        0,10%
        0,05%
                                                                  0,04%
        0,00%
       -0,05%

  'F1: 2021*' er prognosen (stjerne = forventning), 'F1: 2020' er den
  *realiserede* rente fra den seneste refinansiering. Sidstnaevnte er samme
  stoerrelse som tabelformatets foerste raekke ("Lånerente pr. <dato>"), og den
  gemmes derfor som facit-observation paa selve refinansieringsdatoen - ikke paa
  notatets publiceringsdato.

Enkelte udgaver (oktober 2023) tegner soejlerne uden tekstlabels; de giver
ingen prognose, og det opdages ved at det stjernemarkerede akselabel ikke har
nogen talvaerdi i naerheden.

Brug:
    parse_text(text, pub_date)      # teksten fra pdftotext -layout
    parse_pdf_bytes(pdf_bytes, ...) # henter ogsaa publiceringsdatoen fra PDF'en
"""
from __future__ import annotations

import calendar
import datetime as dt
import re

BANK_ID = "jyske"

# 'Figur 2: F3-lån ved januar rentetilpasning 2020 og forventning til 2023'
FIGUR_RE = re.compile(
    r"Figur\s*\d+\s*:\s*F\s*([135])\s*-\s*l[åa]n\s+ved\s+([a-zæøå]+)\s+"
    r"rentetilpasning\s+(\d{4})\s+og\s+forventning\s+til\s+(\d{4})",
    re.IGNORECASE)
# Notatets egen overskrift er den autoritative maaned: i april 2023-udgaven
# siger figur 1 og 2 ved en fejl 'januar' (kopieret fra forrige udgave), mens
# notatet handler om refinansieringen 1. april.
NOTE_RE = re.compile(
    r"Forventning\s+til\s+rentetilpasning\s+pr\.?\s*1\.?\s*([a-zæøå]+)\s+"
    r"(\d{4})", re.IGNORECASE)
# 'F1: 2023*' (stjerne = prognose) og 'F1: 2022' (realiseret)
AXIS_RE = re.compile(r"F\s*([135])\s*:\s*(\d{4})(\*?)")
# Dansk tal med procent: '-0,22%', '2,66 %'
PCT_RE = re.compile(r"(-?\d+,\d+)\s*%")
MONTHS = {"januar": 1, "februar": 2, "marts": 3, "april": 4, "maj": 5,
          "juni": 6, "juli": 7, "august": 8, "september": 9, "oktober": 10,
          "november": 11, "december": 12}
PRODUCT = {"1": "f1", "3": "f3", "5": "f5"}
# Et label hoerer til den naermeste akse; laengere vaek er det en y-aksetal
MAX_LABEL_DISTANCE = 25


def _num(text: str) -> float:
    return round(float(text.replace(".", "").replace(",", ".")), 3)


def _y_axis_column(labels: list[tuple[int, float]]) -> int | None:
    """x-positionen for y-aksens tal (mange labels i samme kolonne)."""
    if not labels:
        return None
    counts: dict[int, int] = {}
    for x, _v in labels:
        counts[x] = counts.get(x, 0) + 1
    x, n = max(counts.items(), key=lambda kv: kv[1])
    return x if n >= 3 else None


def _figure_values(block: list[str]) -> tuple[dict, dict]:
    """Returnerer (prognoser, realiserede) for én figurblok.

    Hvert procenttal tildeles det naermeste akselabel maalt paa x-position,
    praecis som kolonnetildelingen i tabel-parseren. Y-aksens talspalte
    udelades, fordi den ellers ville blive laest som en vaerdi for det
    venstrestaaeende akselabel.
    """
    labels = [(m.start(), _num(m.group(1)))
              for ln in block for m in PCT_RE.finditer(ln)]
    axes = [(m.start(), m.group(2), bool(m.group(3)))
            for ln in block for m in AXIS_RE.finditer(ln)]
    if not labels or not axes:
        return {}, {}

    y_x = _y_axis_column(labels)
    values = [(x, v) for x, v in labels if y_x is None or abs(x - y_x) > 3]

    assigned: dict[int, tuple[float, int]] = {}
    for x, v in values:
        i, (ax, _year, _star) = min(enumerate(axes),
                                    key=lambda kv: abs(kv[1][0] - x))
        if abs(ax - x) > MAX_LABEL_DISTANCE:
            continue
        if i in assigned and assigned[i][1] <= abs(ax - x):
            continue
        assigned[i] = (v, abs(ax - x))

    forecasts: dict[str, tuple[str, float]] = {}
    realized: dict[str, tuple[str, float]] = {}
    for i, (_x, year, star) in enumerate(axes):
        if i not in assigned:
            continue
        v = assigned[i][0]
        (forecasts if star else realized)[year] = v
    return forecasts, realized


def _pub_date_from_pdf(pdf_bytes: bytes) -> str | None:
    """PDF-ens oprettelsesdato - samme dato som tabelformatet bruger."""
    try:
        import io

        import pdfplumber
    except ImportError:
        return None
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            raw = (pdf.metadata or {}).get("CreationDate") or ""
    except Exception:
        return None
    m = re.search(r"D:(\d{4})(\d{2})(\d{2})", raw)
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None


def parse_text(text: str, pub_date: str) -> dict | None:
    """Parse graf-notatet. Returnerer None hvis der ikke er nogen prognose."""
    lines = text.splitlines()
    headings = [(i, FIGUR_RE.search(ln)) for i, ln in enumerate(lines)]
    headings = [(i, m) for i, m in headings if m]
    if not headings:
        return None

    rows: dict[str, dict] = {}
    realized: dict[str, list] = {}
    targets: list[str] = []
    # Notatets overskrift bestemmer maaned og maalaar for alle figurerne.
    note = NOTE_RE.search(text)
    note_month = MONTHS.get(note.group(1).lower()) if note else None
    note_year = int(note.group(2)) if note else None
    for n, (i, m) in enumerate(headings):
        prod = PRODUCT[m.group(1)]
        month = note_month or MONTHS.get(m.group(2).lower())
        if month is None:
            continue
        old_year = int(m.group(3))
        new_year = note_year or int(m.group(4))
        stop = headings[n + 1][0] if n + 1 < len(headings) else i + 40
        forecasts, real = _figure_values(lines[i + 1:stop])
        target = f"{new_year}-{month:02d}-01"
        if str(new_year) in forecasts:
            rows[prod] = {"name": prod, "aktuelt": None,
                          "forecasts": [forecasts[str(new_year)]],
                          "targets": [target]}
            targets.append(target)
        if str(old_year) in real:
            real_date = f"{old_year}-{month:02d}-01"
            realized[prod] = [real_date, real[str(old_year)]]

    if not rows:
        return None
    return {
        "bank": BANK_ID,
        "source": "pdf-forventning-rentetilpasning",
        "capture": None,
        "obs_date": pub_date,
        "pub_date": pub_date,
        "recalc_date": None,
        "targets": targets,
        "rows": rows,
        "raw_rows": {k: [None] + v["forecasts"] for k, v in rows.items()},
        # Realiserede renter fra figuren. De er *ikke* et datapunkt for
        # notatet, men en observation paa refinansieringsdatoen selv, og
        # backfill'en samler dem i data/banks/jyske/facit.json.
        "realized": realized,
        "kind": "boligrenter-graf",
    }


def parse_pdf_bytes(pdf_bytes: bytes, source: str | None = None,
                    capture_ts: str | None = None,
                    fallback_date: str | None = None) -> dict | None:
    from banks.jyske_renteprognose import _text_via_pdftotext

    text = _text_via_pdftotext(pdf_bytes)
    if not text:
        return None
    pub = (_pub_date_from_pdf(pdf_bytes)
           or _edition_month(text)
           or fallback_date
           or dt.date.today().isoformat())
    snap = parse_text(text, pub)
    if snap is None:
        return None
    if source:
        snap["source"] = source
    if capture_ts:
        snap["capture"] = capture_ts
    return snap


def _edition_month(text: str) -> str | None:
    """Reserve for publiceringsdato: 'BOLIGØKONOMI| September 2022'."""
    m = re.search(r"BOLIG[ØO]KONOMI\s*\|\s*([A-Za-zÆØÅæøå]+)\s+(\d{4})",
                  text, re.IGNORECASE)
    if not m:
        return None
    month = MONTHS.get(m.group(1).lower())
    if month is None:
        return None
    year = int(m.group(2))
    return f"{year}-{month:02d}-{calendar.monthrange(year, month)[1]:02d}"


def fetch_and_parse(url: str, source: str = "pdf-forventning-rentetilpasning",
                    capture_ts: str | None = None,
                    fallback_date: str | None = None) -> dict | None:
    import requests

    from common import UA

    r = requests.get(url, headers=UA, timeout=120)
    r.raise_for_status()
    if not r.content.startswith(b"%PDF"):
        return None
    return parse_pdf_bytes(r.content, source, capture_ts,
                           fallback_date or dt.date.today().isoformat())
