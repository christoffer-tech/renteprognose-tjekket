"""Backfill af Jyske Markets' månedlige "Renteprognose" (2017-2026).

Notatet har ingen stabil URL. Udgaverne findes paa to maader:

1. `SEED_URLS` nedenfor - de URL'er der er verificeret i live (Google/arkivet).
   Jyske flytter rundt paa stierne hen over aarene, og Wayback-API'et svarer
   tomt paa de gamle praefikser, saa listen er den primaere kilde.
2. `discover()` - bedste-indsats soegning i Wayback-arkivet efter nye udgaver.

PDF'erne ligger typisk stadig paa jyskebank.dk (HTTP 200), saa de hentes
direkte fra live-siden; arkivet bruges kun til at *finde* URL'erne.

Vigtigt: parseren (`banks/jyske_renteprognose.py`) laeser baade STATSRENTER og
SWAPRENTER. Har der allerede vaeret koert en backfill med en aeldre parser, er
snapshot-filen bevaret og de nye raekker flettet ind, saa en forbedret parser
kan tilfoeje serier uden at hente eller overskrive historik.

Brug:
    python scraper/backfill_jyske_renteprognose.py
    python scraper/backfill_jyske_renteprognose.py --dry-run
    python scraper/backfill_jyske_renteprognose.py --no-discover
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
from common import ROOT

BANK_ID = "jyske"
UA = {"User-Agent": "Mozilla/5.0 renteprognose-tracker (research project)"}


def snap_dir(bank_id: str) -> Path:
    """Snapshot-mappe. Definineret her frem for importeret fra scrape.py, fordi
    scrape.py traekker pdfplumber ind (Sydbank-PDF'er), som ikke er noedvendig
    for at hente og parse Jyske-notaterne."""
    d = ROOT / "data" / "banks" / bank_id / "snapshots"
    d.mkdir(parents=True, exist_ok=True)
    return d

# Verificerede udgaver. Jyske har lagt notaterne under tre forskellige stier
# gennem tiden (wps/wcm/connect/jfo, /pdf/wcm og beta-vaerten), og nogle af
# filnavnene har slaaefejl ('Renteprogose'), som skal bevares for at ramme.
SEED_URLS = [
    # 2017-2019. Bemaerk: filnavnet er ikke til at stole paa - UUID'en
    # aeed7003... hedder 'Februar 2017' men serveres i dag med juninotatet
    # 27.06.2019, og filen er derfor gemt under sin *faktiske* publiceringsdato
    # (parseren laeser datoen fra notatet, ikke fra URL'en).
    "https://www.jyskebank.dk/wps/wcm/connect/jfo/aeed7003-e75c-400e-9859-06ec17dba30a/Renteprognose+Februar+2017.pdf?MOD=AJPERES",
    "https://www.jyskebank.dk/pdf/wcm/f1717261-e5ef-45e2-8ab4-6ce0796b19bf/Renteprognose+Juli+2017.pdf?MOD=AJPERES",
    "https://www.jyskebank.dk/wps/wcm/connect/d39ebd13-0d09-48b4-9299-a8984aabe2bb/Renteprognose+201901.pdf?MOD=AJPERES",
    # Juni 2019 findes i to udgaver: denne har kun grafer og prosa (ingen
    # maskinlaesbar tabel) og giver derfor intet snapshot.
    "https://www.jyskebank.dk/wps/wcm/connect/jfo/eeea4fea-4bb7-47bb-9b57-f03f38f6e193/Renteprognose+Juni+2019.pdf?MOD=AJPERES",
    # 2020
    "https://www.jyskebank.dk/pdf/wcm/08be7926-a1bc-41ff-a1a9-25511141dddc/Renteprognose+januar+2020+-+NY.pdf?MOD=AJPERES",
    "https://www.jyskebank.dk/pdf/wcm/7990897b-95fe-470a-aae7-df5dd311d90b/Renteprognose+September+2020+%28DA%29.pdf?MOD=AJPERES",
    "https://www.jyskebank.dk/pdf/wcm/b71a3678-6fff-4c0e-95ac-d60a31cec65b/Renteprognose+november+2020+%28DA%29.pdf?MOD=AJPERES",
    "https://www.jyskebank.dk/pdf/wcm/1afd855d-2600-4d1c-9039-12cb9870bcb9/Renteprognose+december+2020.pdf?MOD=AJPERES",
    # 2021-2024
    "https://www.jyskebank.dk/wps/wcm/connect/jfo/0b78be34-8fd6-4ece-8cf7-7252b5e62b13/renteprognose-marts-2021.pdf?MOD=AJPERES",
    "https://www.jyskebank.dk/wps/wcm/connect/jfo/3bfe368c-05a8-482c-89f7-6f97213677dc/Renteprogose%2Baugust%2B2021.pdf?MOD=AJPERES",
    "https://www.jyskebank.dk/wps/wcm/connect/jfo/940a7f48-1614-4f5c-a616-b4cbb5f43e47/Renteprognose%2Bjanuar%2B2022%2B%28DA%29.pdf?MOD=AJPERES",
    "https://www.jyskebank.dk/wps/wcm/connect/jfo/550c7f8d-9304-4cf5-b349-187d7756d876/Renteprognose+maj+2022+-+NY.pdf?MOD=AJPERES",
    "https://www.jyskebank.dk/wps/wcm/connect/jfo/58ad2e28-d4b3-4473-8e06-e36dfc2ef641/Renteprognose+april+2024.pdf?MOD=AJPERES",
    "https://www.jyskebank.dk/wps/wcm/connect/jfo/9d8c7444-036f-4e9a-8ab2-b5cc0687a981/Renteprognose+juni+2024.pdf?MOD=AJPERES",
    "https://beta.jyskebank.dk/pdf/wcm/91f7a8fe-fdd6-4e45-a026-ac7ef659b1b5/Renteprognose+oktober+2024.pdf?MOD=AJPERES",
    # 2025
    "https://beta.jyskebank.dk/pdf/wcm/17ede642-dc2b-4ea0-a972-e48653839f99/Renteprognose+februar+2025.pdf?MOD=AJPERES",
    "https://www.jyskebank.dk/pdf/wcm/a641433a-5a44-486e-b7c9-147be5e020e1/Renteprognose+april+2025.pdf?MOD=AJPERES",
]

CDX = "https://web.archive.org/cdx/search/cdx"
PREFIXES = [
    "jyskebank.dk/wps/wcm/connect/jfo/",
    "jyskebank.dk/media/api/content/mediafiles/",
    "jyskebank.dk/pdf/",
    "beta.jyskebank.dk/pdf/",
]
YEARS = range(2015, 2027)
NAME_RE = re.compile(r"renteprognos|renteprogos", re.I)


def discover() -> list[str]:
    """Find arkiverede PDF-URL'er hvis filnavn er en renteprognose.

    Wayback-API'et svarer tomt paa flere af praefikserne i perioder; fejler det,
    er det ikke kritisk, for SEED_URLS daekker de kendte udgaver.
    """
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
                        for row in r.json()[1:]:
                            o = row[0].split("?")[0]
                            if o.lower().endswith(".pdf") and NAME_RE.search(
                                    urllib.parse.unquote(o)):
                                urls.add(o)
                        break
                except Exception:
                    time.sleep(10)
            time.sleep(0.5)
    return sorted(urls)


def merge_rows(existing: dict, new: dict) -> tuple[dict, list[str], list[str]]:
    """Flet nye raekker ind i et eksisterende snapshot.

    Eksisterende vaerdier vinder ved konflikt - en aeldre, verificeret parsing
    skal ikke kunne aendre historiske tal. Returnerer (snapshot, tilfoejede,
    konflikter).
    """
    rows = dict(existing.get("rows") or {})
    added: list[str] = []
    conflicts: list[str] = []
    for key, row in (new.get("rows") or {}).items():
        if key not in rows:
            rows[key] = row
            added.append(key)
            continue
        old = rows[key]
        if (old.get("aktuelt") != row.get("aktuelt")
                or old.get("forecasts") != row.get("forecasts")):
            conflicts.append(key)
    if not added and not conflicts:
        return existing, [], []
    merged = dict(existing)
    merged["rows"] = rows
    merged["raw_rows"] = {k: [v.get("aktuelt")] + list(v.get("forecasts") or [])
                          for k, v in rows.items()}
    return merged, added, conflicts


def main() -> int:
    import requests

    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-discover", action="store_true",
                    help="spring Wayback-soegningen over (kun SEED_URLS)")
    args = ap.parse_args()

    urls = list(SEED_URLS)
    if not args.no_discover:
        extra = discover()
        print(f"wayback fandt {len(extra)} ekstra PDF-URL'er")
        urls += [u for u in extra if u not in urls]

    out_dir = snap_dir(BANK_ID)
    saved = skipped = conflicts_n = failed = 0
    for u in urls:
        name = urllib.parse.unquote(u.split("/")[-1].split("?")[0])
        if args.dry_run:
            print(f"  ville hente {name[:70]}")
            continue
        try:
            r = requests.get(u, headers=UA, timeout=120, allow_redirects=True)
            if not r.content.startswith(b"%PDF"):
                failed += 1
                print(f"  ikke PDF ({r.status_code}): {name[:60]}")
                continue
            snap = jyske_renteprognose.parse_pdf_bytes(
                r.content, "renteprognose", None, "2020-01-01")
            if snap is None:
                failed += 1
                print(f"  ingen tabel: {name[:60]}")
                continue
            path = out_dir / f"rp-{snap['pub_date']}.json"
            if path.exists():
                old = json.loads(path.read_text(encoding="utf-8"))
                snap, added, conflicts = merge_rows(old, snap)
                if conflicts:
                    conflicts_n += len(conflicts)
                    print(f"  ADVARSEL {snap['pub_date']}: {len(conflicts)} "
                          f"raekker afviger fra den gemte fil "
                          f"({', '.join(conflicts[:6])}) - beholder de gamle")
                if not added and not conflicts:
                    skipped += 1
                    print(f"  {snap['pub_date']} i forvejen komplet "
                          f"({len(snap['rows'])} serier)")
                    continue
                path.write_text(json.dumps(snap, ensure_ascii=False, indent=1),
                                encoding="utf-8")
                saved += 1
                print(f"  {snap['pub_date']} opdateret: +{len(added)} serier "
                      f"({', '.join(added[:8])})")
                continue
            path.write_text(json.dumps(snap, ensure_ascii=False, indent=1),
                            encoding="utf-8")
            saved += 1
            print(f"  {snap['pub_date']} ny: {len(snap['rows'])} serier")
        except Exception as e:
            failed += 1
            print(f"  FEJL {type(e).__name__}: {name[:60]}")
        time.sleep(1)

    print(f"\nFaerdig: {saved} gemt/opdateret, {skipped} komplette i forvejen, "
          f"{failed} uden tabel, {conflicts_n} raekke-konflikter")
    return 0


if __name__ == "__main__":
    sys.exit(main())
