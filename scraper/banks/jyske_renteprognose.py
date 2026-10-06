"""Jyske Markets' månedlige "Renteprognose" (PDF).

Hvert notat indeholder en tabel "Jyske Bank renteprognose" med renteforventninger
for Danmark, Eurozonen og USA:

    Jyske Bank renteprognose
        STATSRENTER
        Danmark      Spot     Q3-24   Q4-24   Q1-25   Q2-25   Q4-25
        Leading       3,35     3,10    2,85    2,60    2,35    1,85
        Cibor 3m      3,63     3,35    3,10    2,85    2,65    2,30
        STAT 2y       2,94     2,75    2,45    2,20    2,05    2,00
        STAT 30y      2,58     2,50    2,35    2,25    2,20    2,45

Tabellerne er maskinlaesbar tekst (i modsaetning til graferne i samme PDF), og
serien daekker december 2019 - juni 2024, altsaa praecis det hul Jyske har i
projektet.

Bemaerk: dette er MARKEDSRENTER. STAT 30y svarer til den 30-aarige statsrente,
ikke til bankens 30-aarige realkreditlaan (fast30), som har et andet spread.
Serierne holdes derfor adskilt fra de oevrige produktnoegler.
"""
from __future__ import annotations

import datetime as dt
import re

from common import UA, obs_date_for

BANK_ID = "jyske"

# (raekkelabel i tabellen, kanonisk produktnoegle)
ROWS = [
    (r"^leading$", "leading_dk"),
    (r"^cibor\s*3\s*m$", "cibor3"),
    (r"^cibor\s*6\s*m$", "cibor6"),
    (r"^stat\s*2\s*y$", "stat2"),
    (r"^stat\s*5\s*y$", "stat5"),
    (r"^stat\s*10\s*y$", "stat10"),
    (r"^stat\s*30\s*y$", "stat30"),
]
IGNORE = (r"^stat\s*\d+\s*y\s*-", r"^amn", r"^kilde")

# Omraader: 'Danmark', 'Eurozonen'/'Europa', 'USA'
AREAS = [(r"danmark", "dk"), (r"euro|europa", "eu"), (r"usa|u\.s", "us")]

TABEL_START = "jyske bank renteprognose"

# Kvartalsetiketter: Q1-24 .. Q4-26, evt. 'Q4-21'
# ingen ankre: vi soeger kvartaler inde i en laengere overskrift
QRE = re.compile(r"\bQ([1-4])-(\d{2})\b", re.IGNORECASE)
# Dansk tal: -0,13 -> -0.13
NUMRE = re.compile(r"^-?\d+,\d+$")


def _num(s: str) -> float | None:
    try:
        return round(float(s.replace(".", "").replace(",", ".")), 3)
    except ValueError:
        return None


def parse_text(text: str, source: str, capture_ts: str | None,
               pub_date: str, fallback_date: str) -> dict | None:
    """Parse alle prognosetabeller i notatet."""
    lines = text.splitlines()
    start = None
    for i, ln in enumerate(lines):
        if TABEL_START in ln.lower():
            start = i
            break
    if start is None:
        return None

    rows: dict[str, dict] = {}
    area = None
    quarter_cols: list[str] = []
    blanks = 0
    for ln in lines[start + 1:start + 140]:
        s = re.sub(r"[ \t]+", " ", ln).strip()
        if not s:
            blanks += 1
            if blanks >= 3 and rows:
                break
            continue
        blanks = 0
        low = s.lower()
        # Ny tabel/figur betyder at vi er faerdige med prognosetabellerne
        if rows and re.match(r"^(tabel|figur)\s*\d", low):
            break
        # Kvartalsoverskrift: find dem KUN i den del af linjen der ikke er tal
        head = re.sub(r"-?\d+,\d+", " ", s)
        qs = QRE.findall(head)
        if len(qs) >= 3:
            quarter_cols = [f"{y}-{int(q) * 3:02d}" for q, y in qs]
            if rows:
                break
            continue
        # Omraade som selvstaendig overskrift
        for pat, key in AREAS:
            if re.match(r"^(" + pat + r")\s*$", low):
                area = key
                break
        m = re.match(r"^([a-zæøå0-9\.\- ]+?)\s{1,}((?:-?\d+,\d+\s*)+)$", low)
        if not m:
            continue
        label = m.group(1).strip()
        if any(re.match(p, label) for p in IGNORE):
            continue
        vals = [_num(v) for v in m.group(2).split()]
        vals = [v for v in vals if v is not None]
        if len(vals) < 2:
            continue
        prod = None
        for pat, k in ROWS:
            if re.match(pat, label):
                prod = k
                break
        if prod is None:
            continue
        # Kun Nationalbankens rente er landespecifik; de oevrige serier har
        # kanoniske noegler, saa de kan sammenlignes direkte med andre bankers
        # tilsvarende produkter.
        key = prod if prod == "leading_dk" else prod
        if prod == "leading_dk":
            key = f"leading_{(area or 'dk')}"
        rows[key] = {"name": key, "aktuelt": vals[0], "forecasts": vals[1:]}

    if not rows:
        return None

    # Maal-datoer: kvartalskolonnerne hvis de blev laest, ellers udledes de ikke.
    if quarter_cols and len(quarter_cols) >= max(len(r["forecasts"])
                                                 for r in rows.values()):
        # 'YY-MM' -> sidste dag i kvartalsmaaneden som ISO-dato
        import calendar
        targets = []
        for q in quarter_cols:
            yy, mm = q.split("-")
            y, m = 2000 + int(yy), int(mm)
            targets.append(f"{y}-{m:02d}-{calendar.monthrange(y, m)[1]:02d}")
    else:
        # Uden laesbare kvartalskolonner kan vi ikke fastslaa maaldatoer.
        return None

    return {
        "bank": BANK_ID,
        "source": source,
        "capture": capture_ts,
        "obs_date": obs_date_for(source, capture_ts, fallback_date),
        "pub_date": pub_date,
        "recalc_date": None,
        "targets": targets[:max(len(r["forecasts"]) for r in rows.values())],
        "rows": rows,
        "raw_rows": {k: [v["aktuelt"]] + v["forecasts"]
                     for k, v in rows.items()},
        "kind": "markedsrenter",
    }


def parse_pdf_bytes(pdf_bytes: bytes, source: str, capture_ts: str | None,
                    fallback_date: str) -> dict | None:
    import io

    import pdfplumber
    parts = []
    pub = None
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            parts.append(page.extract_text(layout=True) or "")
    text = "\n".join(parts)
    # Publiceringsdato: foerste dato i dokumentet ('05.03.2018 08:36')
    m = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", text)
    if m:
        pub = f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    return parse_text(text, source, capture_ts, pub or fallback_date, fallback_date)


def fetch_and_parse(url: str, source: str = "renteprognose",
                    capture_ts: str | None = None,
                    fallback_date: str | None = None) -> dict | None:
    import requests
    r = requests.get(url, headers=UA, timeout=120)
    r.raise_for_status()
    if not r.content.startswith(b"%PDF"):
        return None
    return parse_pdf_bytes(r.content, source, capture_ts,
                           fallback_date or dt.date.today().isoformat())
