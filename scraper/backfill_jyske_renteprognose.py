"""Backfill af Jyske Markets' månedlige "Renteprognose" (2019-2024).

Notatet har ingen stabil URL, saa udgaverne findes via Wayback-arkivets indeks
over filnavne-mønstret *renteprognose*. Hver udgave har sin egen UUID, og
PDF'erne ligger stadig paa jyskebank.dk (HTTP 200), saa de hentes direkte fra
live-siden — arkivet bruges kun til at *finde* URL'erne.

Brug:
    python scraper/backfill_jyske_renteprognose.py
    python scraper/backfill_jyske_renteprognose.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from banks import jyske_renteprognose
from scrape import _save_if_new, snap_dir

BANK_ID = "jyske"
CDX = "https://web.archive.org/cdx/search/cdx"
# Stier hvor Jyske har lagt notaterne gennem tiden. Vi spoerger CDX pr. sti OG
# pr. aar, for et bredt prefix rammer API'ets graense paa 5000 raekker og
# dermed skjuler de nyeste udgaver.
PREFIXES = [
    "jyskebank.dk/wps/wcm/connect/jfo/",
    "jyskebank.dk/media/api/content/mediafiles/",
    "jyskebank.dk/pdf/",
]
YEARS = range(2015, 2027)
NAME_RE = re.compile(r"renteprognos|renteprogos", re.I)
UA = {"User-Agent": "Mozilla/5.0 renteprognose-tracker (research project)"}


def discover() -> list[str]:
    """Find alle arkiverede PDF-URL'er hvis filnavn er en renteprognose."""
    import requests

    urls: set[str] = set()
    for prefix in PREFIXES:
        for year in YEARS:
            for attempt in range(3):
                try:
                    r = requests.get(CDX, params={
                        "url": prefix, "matchType": "prefix",
                        "from": str(year), "to": str(year), "output": "json",
                        "fl": "original", "collapse": "urlkey", "limit": "5000",
                    }, headers=UA, timeout=200)
                    if r.status_code == 200 and r.content.strip().startswith(b"["):
                        data = r.json()
                        n = 0
                        for row in data[1:]:
                            o = row[0].split("?")[0]
                            if o.lower().endswith(".pdf") and NAME_RE.search(
                                    urllib.parse.unquote(o)):
                                urls.add(o)
                                n += 1
                        if n:
                            print(f"  {prefix.split('/')[3]:12s} {year}: {n} traef")
                        break
                except Exception:
                    time.sleep(10)
            time.sleep(0.5)
    return sorted(urls)


def main() -> int:
    import requests

    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    urls = discover()
    print(f"fandt {len(urls)} arkiverede renteprognose-PDF'er")

    seen: set[str] = set()
    saved = skipped = failed = 0
    for u in urls:
        if "vaekst" in u.lower() or "vækst" in u.lower():
            continue
        if args.dry_run:
            print(f"  ville hente {urllib.parse.unquote(u.split('/')[-1])[:60]}")
            continue
        try:
            r = requests.get(u, headers=UA, timeout=90, allow_redirects=True)
            if not r.content.startswith(b"%PDF"):
                failed += 1
                continue
            snap = jyske_renteprognose.parse_pdf_bytes(
                r.content, "renteprognose", None, "2020-01-01")
            if snap is None:
                failed += 1
                continue
            # dedup paa publiceringsdato + indhold
            key = snap["pub_date"] + json.dumps(snap["rows"], sort_keys=True)
            if key in seen:
                skipped += 1
                continue
            seen.add(key)
            name = f"rp-{snap['pub_date']}.json"
            if (snap_dir(BANK_ID) / name).exists():
                skipped += 1
                continue
            _save_if_new(BANK_ID, snap, name)
            saved += 1
            print(f"  {snap['pub_date']}  {len(snap['rows'])} serier  "
                  f"({urllib.parse.unquote(u.split('/')[-1])[:44]})")
        except Exception as e:
            failed += 1
            if failed <= 3:
                print(f"  FEJL {type(e).__name__}: "
                      f"{urllib.parse.unquote(u.split('/')[-1])[:50]}")
        time.sleep(1)

    print(f"\nFærdig: {saved} nye, {skipped} kendte, {failed} uden tabel")
    return 0


if __name__ == "__main__":
    sys.exit(main())
