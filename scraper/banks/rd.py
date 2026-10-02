"""Realkredit Danmark-parser (prognoseside).

Prognoseside: rd.dk/kurser-og-renter/renteprognose
- FlexLån F1/F3/F5 som INTERVALLER ('2,9 % - 3,2 %'), relative horisonter
  3/6/12 mdr. -> gemmes som {"lo":.., "hi":..}; midtpunkt bruges til fejl,
  interval til hit-rate.
- FlexKort med 'Aktuel rente' + faste datoer (1. januar / 1. juli).
- Kurs-tabellen (obligationskurser) springes over - anden enhed.
- Hver række får sin egen 'targets'-liste, da FlexLån og FlexKort bruger
  forskellige måldatoer.
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup

from common import (add_months, clean, obs_date_for, parse_dk_date,
                    parse_interval, parse_rate, table_rows)

BANK_ID = "rd"
LABEL = "Realkredit Danmark"
PAGE_URL = "https://rd.dk/kurser-og-renter/renteprognose"
FACIT_URL = "https://rd.dk/laantyper/flexlaan-k/renteudvikling"

REF_MONTHS = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "maj": 5, "may": 5,
              "jun": 6, "jul": 7, "aug": 8, "sep": 9, "okt": 10, "oct": 10,
              "nov": 11, "dec": 12}


def canonical_product(name: str) -> str | None:
    n = name.lower()
    if "flexkort" in n or "flex kort" in n:
        return "fkort"
    if "flexlån" in n or "flexlan" in n:
        if re.search(r"\bf1\b", n):
            return "f1"
        if re.search(r"\bf3\b", n):
            return "f3"
        if re.search(r"\bf5\b", n):
            return "f5"
    return None


def parse_cell(text: str):
    """Interval -> {'lo':..,'hi':..}, ellers enkeltværdi eller None."""
    iv = parse_interval(text)
    if iv is not None:
        return {"lo": iv[0], "hi": iv[1]}
    return parse_rate(text)


def parse_snapshot(html: str, source: str, capture_ts: str | None,
                   fallback_date: str) -> dict | None:
    soup = BeautifulSoup(html, "lxml")
    txt = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
    pub_date = None
    m = re.search(r"renteprognose\s+pr\.\s+(\d{1,2}\.\s*[a-zæøå]+\s*\d{4})",
                  txt, re.IGNORECASE)
    if m:
        pub_date = parse_dk_date(m.group(1))
    if pub_date is None:
        pub_date = fallback_date

    data_rows: dict[str, dict] = {}
    raw_rows: dict[str, list] = {}
    all_targets: set[str] = set()

    for t in soup.find_all("table"):
        rows = table_rows(t)
        if len(rows) < 2:
            continue
        kinds = [canonical_product(clean(r[0])) for r in rows[1:] if r]
        if not any(k in ("f1", "f3", "f5", "fkort") for k in kinds):
            continue

        hdr_text = " ".join(rows[0]).lower()
        if "aktuel" in hdr_text:
            # FlexKort-tabel: 'Aktuel rente' + faste datoer
            dates = [parse_dk_date(c) for c in rows[0]]
            akt_col = next((i for i, c in enumerate(rows[0])
                            if "aktuel" in c.lower()), None)
            for r, kind in zip(rows[1:], kinds):
                if kind != "fkort":
                    continue
                name = clean(r[0])
                vals = [parse_cell(c) for c in r[1:]]
                # justér: første celle efter navn svarer til rows[0][1]
                cols = list(range(1, len(rows[0])))
                aktuelt = None
                tgts, fcs = [], []
                for ci, v in zip(cols, vals):
                    if akt_col is not None and ci == akt_col:
                        aktuelt = v if not isinstance(v, dict) else \
                            round((v["lo"] + v["hi"]) / 2, 3)
                    elif ci < len(dates) and dates[ci]:
                        tgts.append(dates[ci])
                        fcs.append(v)
                if not tgts:
                    continue
                data_rows["fkort"] = {"name": name, "aktuelt": aktuelt,
                                      "forecasts": fcs, "targets": tgts}
                raw_rows[name] = [aktuelt] + fcs
                all_targets.update(tgts)
        else:
            # FlexLån-intervaltabel: relative mdr.-horisonter
            offsets = [int(x) for x in
                       re.findall(r"(\d+)\s*mdr", " ".join(rows[0]))]
            n_cols = max(len(r) - 1 for r in rows[1:] if r)
            if len(offsets) < n_cols:
                # evt. opsplittede headerceller ('3' | 'mdr.'): find tal i rækkefølge
                offsets = [int(x) for x in re.findall(r"(\d+)", " ".join(rows[0]))]
            if len(offsets) < n_cols:
                continue
            offsets = offsets[:n_cols]
            tgts = [add_months(pub_date, o) for o in offsets]
            for r, kind in zip(rows[1:], kinds):
                if kind not in ("f1", "f3", "f5"):
                    continue
                name = clean(r[0])
                if "eur" in name.lower():
                    continue
                vals = [parse_cell(c) for c in r[1:]]
                while len(vals) < len(tgts):
                    vals.append(None)
                data_rows[kind] = {"name": name, "aktuelt": None,
                                   "forecasts": vals[:len(tgts)],
                                   "targets": list(tgts)}
                raw_rows[name] = [None] + vals[:len(tgts)]
                all_targets.update(tgts)

    if not data_rows:
        return None

    return {
        "bank": BANK_ID,
        "source": source,
        "capture": capture_ts,
        "obs_date": obs_date_for(source, capture_ts, fallback_date),
        "pub_date": pub_date,
        "recalc_date": None,
        "targets": sorted(all_targets),
        "rows": data_rows,
        "raw_rows": raw_rows,
    }


def parse_ref_date(text: str) -> str | None:
    """'apr-26' -> '2026-04-01'. Månedsforkortelser på da/en."""
    m = re.search(r"([a-z]+)\s*[-–]\s*(\d{2,4})", text.strip().lower())
    if not m:
        return None
    month = REF_MONTHS.get(m.group(1)[:3])
    if month is None:
        return None
    y = int(m.group(2))
    if y < 100:
        y += 2000 if y < 70 else 1900
    return f"{y:04d}-{month:02d}-01"


def parse_facit(html: str) -> dict[str, list]:
    """Parser renteudvikling-siden -> {f1: [[dato, værdi]...], f3:..., f5:...}.

    Bruger DKK-tabellen 'Med afdrag' (kontantlånsrente inkl. kursfradrag -
    samme definition som prognosen).
    """
    soup = BeautifulSoup(html, "lxml")
    series: dict[str, list] = {"f1": [], "f3": [], "f5": []}
    for t in soup.find_all("table"):
        rows = table_rows(t)
        if not rows or "ref. dato" not in (rows[0][0].lower() if rows[0] else ""):
            continue
        # kun DKK 'med afdrag' (ikke EUR / 'uden afdrag')
        head = t.find_previous(["h1", "h2", "h3"])
        htxt = head.get_text(" ", strip=True).lower() if head else ""
        if "eur" in htxt:
            continue
        hdr = [c.lower() for c in rows[0]]
        if not any("med afdrag" in c and "uden" not in c for c in hdr):
            continue
        cols = {}
        for j, c in enumerate(hdr[1:], start=1):
            if re.search(r"\bf1\b", c):
                cols["f1"] = j
            elif re.search(r"\bf3\b", c):
                cols["f3"] = j
            elif re.search(r"\bf5\b", c):
                cols["f5"] = j
        if not cols:
            continue
        for r in rows[1:]:
            d = parse_ref_date(r[0])
            if not d:
                continue
            for key, j in cols.items():
                if j < len(r):
                    v = parse_rate(r[j] if "%" in r[j] else r[j] + " %")
                    if v is not None:
                        series[key].append([d, v])
    for key in series:
        dedup: dict[str, float] = {}
        for d, v in sorted(series[key]):
            dedup[d] = v
        series[key] = [[d, v] for d, v in sorted(dedup.items())]
    return series
