"""Scraper Nykredits renteprognose.

Henter prognosetabellen fra den live side eller fra Wayback Machine-snapshots,
parser den til et normaliseret snapshot og gemmer som JSON i data/snapshots/.

Brug:
    python scrape.py update     # hent live-side, gem hvis der er nyt indhold
    python scrape.py backfill   # hent alle historiske snapshots via Wayback Machine
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
SNAP_DIR = ROOT / "data" / "snapshots"
SNAP_DIR.mkdir(parents=True, exist_ok=True)

LIVE_URL = "https://www.nykredit.dk/dit-liv/bolig/kurser/renteprognose/"
CDX_URL = "https://web.archive.org/cdx/search/cdx"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) renteprognose-tracker (research project)"}

PRODUCT_LABELS = {
    "cita3": "CITA3",
    "cita6": "CITA6",
    "fkort": "F-kort",
    "f1": "F1",
    "f3": "F3",
    "f5": "F5",
    "fast20": "Fast rente 20 år",
    "fast30": "Fast rente 30 år",
}


def canonical_product(name: str) -> str | None:
    """Normaliser rækkenavn til kanonisk nøgle. Returner None hvis ukendt."""
    n = name.lower().replace("\u200b", " ").strip()
    n = re.sub(r"\s+", " ", n)
    # Alle match er forankret i starten af rækkenavnet, da parenteser kan
    # nævne andre produkter (fx 'CITA6 (indgår i rente på F-kort)')
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


def parse_rate(text: str) -> float | None:
    m = re.search(r"(-?[\d\s\u00a0\u202f.,]+)\s*%", text.replace("\u200b", ""))
    if not m:
        return None
    num = m.group(1).replace(" ", "").replace("\u00a0", "").replace("\u202f", "")
    # dansk komma-decimal; punktum som tusindtalsseparator fjernes kun hvis der også er komma
    if "," in num:
        num = num.replace(".", "").replace(",", ".")
    try:
        return round(float(num), 3)
    except ValueError:
        return None


def parse_dk_date(text: str) -> str | None:
    """'30-12-26' eller '30-12-2026' -> '2026-12-30'. Returner None hvis ugyldig."""
    m = re.search(r"(\d{1,2})-(\d{1,2})-(\d{2,4})", text)
    if not m:
        return None
    d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if y < 100:
        y += 2000 if y < 70 else 1900
    try:
        return dt.date(y, mo, d).isoformat()
    except ValueError:
        return None


def parse_transposed(rows: list[list[str]]) -> tuple | None:
    """Parser det gamle (transponerede) tabellayout.

    Første række er produktnavne, efterfølgende rækker er
    ['Aktuelt'|måldato, værdi, ...]. Returner (targets, data_rows, raw_rows).
    """
    if not rows or len(rows) < 3:
        return None
    header = rows[0]
    offset = 1 if not header[0].strip() else 0
    names = [re.sub(r"\s+", " ", c.replace("\u200b", " ")).strip()
             for c in header[offset:]]
    keys = [canonical_product(n) for n in names]
    if sum(k is not None for k in keys) < 2:
        return None
    aktuelt_vals: list = [None] * len(names)
    date_rows: list[tuple[str, list]] = []
    for r in rows[1:]:
        vals = r[offset:]
        if not vals:
            continue
        label = re.sub(r"\s+", " ", r[0].replace("\u200b", " ")).strip()
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
            print(f"    ADVARSEL: '{name}' kolliderer med tidligere række "
                  f"for '{key}' - beholder den første", flush=True)
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


def obs_date_for(source: str, capture_ts: str | None, today: str) -> str:
    """Dato for hvornår 'Aktuelt' er observeret: capture-dato (wayback) eller i dag (live)."""
    if capture_ts:
        return f"{capture_ts[0:4]}-{capture_ts[4:6]}-{capture_ts[6:8]}"
    return today


def parse_snapshot(html: str, source: str, capture_ts: str | None,
                   fallback_date: str) -> dict | None:
    soup = BeautifulSoup(html, "lxml")
    # prognosetabellen er den tabel der indeholder 'Aktuelt'
    table = None
    for t in soup.find_all("table"):
        if "ktuelt" in t.get_text():
            table = t
            break
    if table is None:
        return None

    rows = [[c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
            for tr in table.find_all("tr")]
    rows = [r for r in rows if any(c.strip() for c in r)]
    if not rows:
        return None

    header_idx = next((i for i, r in enumerate(rows)
                       if any("ktuelt" in c for c in r)), None)
    data_rows: dict[str, dict] = {}
    raw_rows: dict[str, list] = {}
    targets: list[str | None] = []

    if header_idx is not None and any(
            parse_dk_date(c) for c in rows[header_idx][1:]):
        # standard-layout: produkter som rækker, måldatoer som kolonner.
        # Måldatoerne står EFTER 'Aktuelt'-kolonnen (første celle er et tomt hjørnefelt).
        hdr = rows[header_idx]
        akt_col = next(i for i, c in enumerate(hdr) if "ktuelt" in c)
        targets = [parse_dk_date(c) for c in hdr[akt_col + 1:]]
        for r in rows[header_idx + 1:]:
            if len(r) <= akt_col:
                continue
            name = re.sub(r"\s+", " ", r[0].replace("\u200b", " ")).strip()
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
                print(f"    ADVARSEL: '{name}' kolliderer med tidligere række "
                      f"for '{key}' - beholder den første", flush=True)
                continue
            data_rows[key] = {"name": name, "aktuelt": aktuelt,
                              "forecasts": forecasts}
    else:
        # gammelt layout (pre-okt 2022): produkter som kolonner, datoer som rækker
        transposed = parse_transposed(rows)
        if transposed is None:
            return None
        targets, data_rows, raw_rows = transposed

    if not data_rows:
        return None

    # "Seneste renteprognose ... er fra 14-09-2026 og genberegnet den 29-09-2026"
    txt = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
    pub_date = recalc_date = None
    m = re.search(r"er fra\s+(\d{1,2}-\d{1,2}-\d{2,4})"
                  r"(?:\s+og genberegnet den\s+(\d{1,2}-\d{1,2}-\d{2,4}))?", txt)
    if m:
        pub_date = parse_dk_date(m.group(1))
        if m.group(2):
            recalc_date = parse_dk_date(m.group(2))
    if pub_date is None:
        pub_date = fallback_date

    return {
        "source": source,
        "capture": capture_ts,
        "obs_date": obs_date_for(source, capture_ts, fallback_date),
        "pub_date": pub_date,
        "recalc_date": recalc_date,
        "targets": targets,
        "rows": data_rows,
        "raw_rows": raw_rows,
    }


def fetch(url: str, timeout: int = 60) -> str:
    for attempt in range(3):
        try:
            r = requests.get(url, headers=UA, timeout=timeout)
            r.raise_for_status()
            r.encoding = r.apparent_encoding or "utf-8"
            return r.text
        except requests.RequestException as e:
            print(f"    forsøg {attempt + 1} fejlede ({e}), venter...", flush=True)
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"Kunne ikke hente {url}")


def snapshot_fingerprint(snap: dict) -> str:
    core = {k: v for k, v in snap.items() if k not in ("source", "capture")}
    return json.dumps(core, sort_keys=True)


def cmd_update() -> None:
    print("Henter live-side...", flush=True)
    html = fetch(LIVE_URL)
    today = dt.date.today().isoformat()
    snap = parse_snapshot(html, "live", None, today)
    if snap is None:
        sys.exit("FEJL: kunne ikke parse prognosetabellen på live-siden")
    print(f"  pub_date={snap['pub_date']} produkter={sorted(snap['rows'])}", flush=True)

    existing = sorted(SNAP_DIR.glob("*.json"))
    if existing:
        latest = json.loads(existing[-1].read_text(encoding="utf-8"))
        if snapshot_fingerprint(latest) == snapshot_fingerprint(snap):
            print(f"Ingen ændring siden {existing[-1].name} - gemmer ikke.", flush=True)
            return
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M")
    out = SNAP_DIR / f"live-{stamp}.json"
    out.write_text(json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Gemt {out.name}", flush=True)


def list_captures() -> list[dict]:
    params = {
        "url": "nykredit.dk/dit-liv/bolig/kurser/renteprognose/",
        "from": "2020",
        "output": "json",
        "filter": ["statuscode:200", "mimetype:text/html"],
        "collapse": "digest",
    }
    print("Henter capture-liste fra Wayback CDX...", flush=True)
    r = requests.get(CDX_URL, params=params, headers=UA, timeout=120)
    r.raise_for_status()
    data = r.json()
    header, rows = data[0], data[1:]
    captures = [dict(zip(header, row)) for row in rows]
    print(f"  {len(captures)} unikke captures fundet", flush=True)
    return captures


def cmd_backfill() -> None:
    captures = list_captures()
    new, skipped, failed = 0, 0, 0
    for cap in captures:
        ts = cap["timestamp"]
        out = SNAP_DIR / f"{ts}.json"
        if out.exists():
            skipped += 1
            continue
        url = f"https://web.archive.org/web/{ts}id_/{cap['original']}"
        try:
            html = fetch(url)
        except RuntimeError:
            failed += 1
            continue
        fallback = f"{ts[0:4]}-{ts[4:6]}-{ts[6:8]}"
        snap = parse_snapshot(html, "wayback", ts, fallback)
        if snap is None:
            print(f"  {ts}: ingen tabel fundet", flush=True)
            failed += 1
            continue
        out.write_text(json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"  {ts}: pub={snap['pub_date']} produkter={len(snap['rows'])} OK", flush=True)
        new += 1
        time.sleep(1)  # vær sød ved archive.org
    print(f"Færdig: {new} nye, {skipped} eksisterende sprunget over, {failed} fejlede", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["update", "backfill"])
    args = ap.parse_args()
    if args.cmd == "update":
        cmd_update()
    else:
        cmd_backfill()


if __name__ == "__main__":
    main()
