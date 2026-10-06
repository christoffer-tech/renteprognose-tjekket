"""Jyske Realkredits kvartalsnotater — "Boliglånsanbefaling".

Notatet indeholder en tabel af samme type som HTML-siden:

    Forventninger til realkreditrenten
                           Jyske Rente-   Jyske Rente-til-  Jyske Rente-   Jyske Fast Rente
     Lånerente pr.         tilpasning F1  pasning F3        tilpasning F5  (30år)
      03-01-2024               3,65%          2,74%             2,64%          5,00%
      03-04-2024               3,21%          2,64%             2,58%          5,00%

Tabellen har flere måldatoer end HTML-siden og er det eneste sted Jyskes
F1/F3/F5-forventninger findes som maskinlæsbar tekst. Selve prognosen findes
ellers kun som grafer i "Renteprognose"- og "forventning til
rentetilpasning"-PDF'erne.

Bemaerk: raekkerne har eksplicitte datoer (typisk d. 3. i en maaned), ikke
faste maanedsoffsets. Vi bruger datoerne fra tabellen direkte som targets.
Kolonnemapping sker paa x-koordinater, fordi overskrifterne er skrevet over to
linjer ('Jyske Rente-' / 'tilpasning F1') og raekkefoelgen i teksten derfor
snyder.
"""
from __future__ import annotations

import datetime as dt
import io
import re

import pdfplumber

from common import UA, obs_date_for

BANK_ID = "jyske"

# Det eneste aeldre kvartalsnotat der er bevaret i arkivet. CDX-indekset viser
# 20+ andre, men deres WARC-indhold er vaek (404 ved afspilning), og de gamle
# /wps/wcm/connect/jfo/-URL'er svarer 403/404.
Q1_2024_URL = ("https://web.archive.org/web/20240221id_/"
               "https://www.jyskebank.dk/media/api/content/mediafiles/"
               "a0tjabgy/boliglaansanbefaling-1-kvartal-2024.pdf")
Q1_2024_PUB = "2024-01-04"

# Den stabile "nyeste udgave"-URL. Nye kvartaler offentliggoeres her, saa
# serien vokser med én post pr. kvartal.
LIVE_URL = "https://www.jyskebank.dk/pdf/qqcnz2ut/boliglaansanbefaling.pdf"

TABLE_HEADING = "forventninger til realkreditrenten"

HEADER_ANCHORS = [
    (r"^F1$", "f1"),
    (r"^F3$", "f3"),
    (r"^F5$", "f5"),
    (r"^\(30", "fast30kupon"),
]
DEFAULT_ORDER = ["f1", "f3", "f5", "fast30kupon"]

RATE_MIN, RATE_MAX = -2.0, 12.0


def _num(text: str) -> float | None:
    """Tal fra en PDF-token. Bloedt bindetegn (u00ad) betyder minus her."""
    t = (text or "").replace("\u00ad", "-").replace("\u2212", "-").replace("\u00a0", " ")
    m = re.search(r"(-?\d+(?:[.,]\d+)?)", t)
    if not m:
        return None
    try:
        return round(float(m.group(1).replace(",", ".")), 3)
    except ValueError:
        return None


def _is_value(text: str) -> bool:
    t = (text or "").strip().replace("\u00ad", "-")
    return bool(re.match(r"^-?\d+,\d+%?$", t))


def _pages_words(pdf_bytes: bytes) -> tuple[list[list[dict]], str | None]:
    pages: list[list[dict]] = []
    created = None
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        raw = (pdf.metadata or {}).get("CreationDate") or ""
        m = re.search(r"D:(\d{4})(\d{2})(\d{2})", str(raw))
        if m:
            created = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
        for page in pdf.pages:
            pages.append(page.extract_words())
    return pages, created


def _table_on_page(words: list[dict]) -> dict | None:
    """Parse tabellen hvis den staar paa denne side, ellers None."""
    head = None
    for w in words:
        if w["text"] == "Forventninger":
            head = w
            break
    if head is None:
        return None

    band = [w for w in words if head["top"] < w["top"] <= head["top"] + 34]
    found: dict[str, float] = {}
    for w in band:
        for pat, key in HEADER_ANCHORS:
            if key not in found and re.match(pat, w["text"].strip()):
                found[key] = w["x0"]

    by_top: dict[float, list[dict]] = {}
    for w in words:
        if w["top"] <= head["top"] + 30:
            continue
        by_top.setdefault(round(w["top"]), []).append(w)

    rows: list[tuple[str, list[float]]] = []
    for top in sorted(by_top):
        line = sorted(by_top[top], key=lambda z: z["x0"])
        m = re.match(r"^(\d{2})-(\d{2})-(\d{4})$", line[0]["text"].strip())
        if not m:
            if rows:
                break
            continue
        vals = [v for v in (_num(w["text"]) for w in line[1:]
                            if _is_value(w["text"])) if v is not None]
        if len(vals) != 4:
            if rows:
                break
            continue
        rows.append((f"{m.group(3)}-{m.group(2)}-{m.group(1)}", vals))
    if not rows:
        return None

    if len(found) == len(HEADER_ANCHORS):
        keys = sorted(found, key=lambda k: found[k])
    else:
        keys = DEFAULT_ORDER

    per_key: dict[str, list[float]] = {k: [] for k in keys}
    targets: list[str] = []
    for date, vals in rows:
        targets.append(date)
        for k, v in zip(keys, vals):
            per_key[k].append(v)

    flat = [v for vs in per_key.values() for v in vs]
    if not flat or min(flat) < RATE_MIN or max(flat) > RATE_MAX:
        return None
    return {"keys": keys, "targets": targets, "per_key": per_key}


def parse_pdf(pdf_bytes: bytes, source: str, capture_ts: str | None,
              fallback_date: str) -> dict | None:
    pages, created = _pages_words(pdf_bytes)

    table = None
    for words in pages:
        table = _table_on_page(words)
        if table:
            break
    if not table:
        return None

    pub = created or fallback_date
    keys = table["keys"]
    all_targets = table["targets"]
    per_key = table["per_key"]

    # Tabellens foerste raekke er 'Lånerente pr. <dato>' — niveauet ved
    # publiceringen, ikke en prognose. Den bliver derfor 'aktuelt', praecis som
    # HTML-sidens forankring, og indgaar ikke som maal. De oevrige raekker er
    # prognoser og skal ligge efter publiceringsdatoen.
    data_rows: dict[str, dict] = {}
    for k in keys:
        if len(per_key[k]) < 2:
            continue
        data_rows[k] = {"name": k, "aktuelt": per_key[k][0],
                        "forecasts": per_key[k][1:]}
    if not data_rows:
        return None

    targets = all_targets[1:]
    if any(t <= pub for t in targets):
        # Falder tilbage til den raekke hvis dato ligger naermest og ikke efter
        # publiceringen, hvis skabelonen en dag aendrer raekkefoelge.
        idx = 0
        for i, d in enumerate(all_targets):
            if d <= pub:
                idx = i
        targets = [d for i, d in enumerate(all_targets) if i != idx]
        for k in data_rows:
            data_rows[k] = {"name": k, "aktuelt": per_key[k][idx],
                            "forecasts": [v for i, v in enumerate(per_key[k])
                                          if i != idx]}

    return {
        "bank": BANK_ID,
        "source": source,
        "capture": capture_ts,
        "obs_date": obs_date_for(source, capture_ts, fallback_date),
        "pub_date": pub,
        "recalc_date": None,
        "targets": targets,
        "rows": data_rows,
        "raw_rows": {k: [v["aktuelt"]] + v["forecasts"]
                     for k, v in data_rows.items()},
    }


def fetch_and_parse(url: str, source: str = "pdf-boliglaansanbefaling",
                    capture_ts: str | None = None,
                    fallback_date: str | None = None) -> dict | None:
    import requests
    r = requests.get(url, headers=UA, timeout=120)
    r.raise_for_status()
    if not r.content.startswith(b"%PDF"):
        return None
    return parse_pdf(r.content, source, capture_ts,
                     fallback_date or dt.date.today().isoformat())
