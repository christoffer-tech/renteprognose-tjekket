"""Hent realiserede markedsrenter fra Danmarks Statistik som facit-serie.

Jyske Markets' "Renteprognose" spaar om markedsrenter (statsserenter, Cibor,
Nationalbankens rente). De realiserede vaerdier findes i Danmarks Statistiks
tabel MPK3 ("Rentesatser, ultimo (procent p.a.) efter type og tid"), som er
maanedlig tilbage til 1985 og derfor daekker hele prognoseperioden.

Uden denne serie har markedsrente-prognoserne fra 2019-2024 intet facit, fordi
Jyskes egne observationer foerst begynder i 2024.

Brug:
    python scraper/fetch_facit.py            # hent og gem
    python scraper/fetch_facit.py --check    # sammenlign med gemt fil
"""
from __future__ import annotations

import argparse
import calendar
import csv
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "banks" / "jyske" / "facit.json"

API = "https://api.statbank.dk/v1/data"

# produktnoegle i datasættet -> TYPE-kode i MPK3
CODES = {
    "stat10": "5500701004",   # 10 årig statsobligation
    "cibor3": "6059",         # CIBOR, løbetid 3 måneder
    "leading_dk": "5500602011",  # Nationalbankens udlånsrente
}


def fetch(codes: dict[str, str], timeout: int = 180) -> dict[str, list]:
    import requests

    body = {
        "table": "MPK3",
        "format": "CSV",
        # Uden dette returnerer API'et seriernes etiketter i stedet for koder
        "valuePresentation": "Code",
        "variables": [
            {"code": "TYPE", "values": list(codes.values())},
            {"code": "Tid", "values": ["*"]},
        ],
    }
    r = requests.post(API, json=body, timeout=timeout)
    r.raise_for_status()
    text = r.content.decode("utf-8-sig")
    rev = {v: k for k, v in codes.items()}

    series: dict[str, list] = {k: [] for k in codes}
    for row in csv.DictReader(io.StringIO(text), delimiter=";"):
        t = (row.get("TID") or "").strip()
        if len(t) < 6 or t[4] != "M":
            continue
        try:
            year, month = int(t[:4]), int(t[5:7])
        except ValueError:
            continue
        raw = (row.get("INDHOLD") or "").strip()
        if raw in ("..", "", "-"):
            continue
        key = rev.get((row.get("TYPE") or "").strip())
        if key is None:
            continue
        try:
            val = float(raw.replace(".", "").replace(",", "."))
        except ValueError:
            continue
        last = calendar.monthrange(year, month)[1]
        series[key].append([f"{year}-{month:02d}-{last:02d}", val])

    for k in series:
        series[k].sort()
    return series


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    try:
        series = fetch(CODES)
    except Exception as e:
        print(f"Kunne ikke hente MPK3: {type(e).__name__}: {e}")
        return 1

    for k, v in series.items():
        if not v:
            print(f"ADVARSEL: {k} er tom")
        else:
            print(f"{k:12s} {len(v):4d} maanedsobservationer  "
                  f"{v[0][0]} .. {v[-1][0]}  (sidste: {v[-1][1]})")

    if args.check:
        if not OUT.exists():
            print(f"\n{OUT} findes ikke")
            return 1
        old = json.loads(OUT.read_text(encoding="utf-8"))
        for k in series:
            o, n = len(old.get(k, [])), len(series[k])
            print(f"  {k:12s} gemt={o:4d} hentet={n:4d} "
                  f"{'OK' if abs(o - n) <= 2 else 'AFVIGER'}")
        return 0

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(series, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"\nskrev {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
