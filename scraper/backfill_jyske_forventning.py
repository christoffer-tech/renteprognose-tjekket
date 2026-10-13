"""Backfill af Jyske Realkredits boliglånsnotater (2020-2025).

Notaterne skifter format undervejs, og de hentes derfor gennem to parsere:

- 2020-2023: "Forventning til rentetilpasning pr. 1. <maaned>" med én figur pr.
  produkt. Laeses af `banks/jyske_anbefaling.py` (graflabels).
- 2024-: "Forventninger til realkreditrenten" som tabel. Laeses af
  `banks/jyske_pdf.py` (pdfplumber).

Faelles for dem er, at de oplyser Jyskes F1/F3/F5-renter *ekskl. kursskæring* —
samme rentebegreb som HTML-siden, der er hovedkilden. Notaterne ligger ikke
laengere paa jyskebank.dk (404), saa de hentes fra Wayback-arkivet. Alle URL'er
nedenfor er verificeret der.

Figuren indeholder ogsaa den *realiserede* rente fra den seneste
refinansiering ("F1: 2022" ved siden af prognosen "F1: 2023*"). Den er samme
stoerrelse som tabelformatets foerste raekke ("Lånerente pr. <dato>") og samles
i `data/banks/jyske/facit.json` som ekstern facit-serie - dateret paa
refinansieringsdatoen, ikke paa notatets publiceringsdato. Uden den ville
prognoserne fra 2020-2023 staa uden facit.

Brug:
    python scraper/backfill_jyske_forventning.py
    python scraper/backfill_jyske_forventning.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from banks import jyske_anbefaling, jyske_resultat
from common import ROOT, UA

BANK_ID = "jyske"

# (wayback-timestamp, original-URL). Rækkefølgen er ligegyldig.
ARCHIVE_URLS = [
    ("20210117151122", "https://www.jyskebank.dk/wps/wcm/connect/jfo/e8931be7-8f43-45d6-ab71-2d8d5324d775/anbefaling-rentetilpasning-april-2021.pdf?MOD=AJPERES&CVID=noD-0FG"),
    ("20210802013419", "https://www.jyskebank.dk/wps/wcm/connect/jfo/8b1fe84c-edc8-40a2-8638-271055fffaa1/anbefaling_rentetilpasning_oktober.pdf?MOD=AJPERES&CVID=nDcMHsE"),
    ("20220625203526", "https://www.jyskebank.dk/wps/wcm/connect/jfo/5472f047-2298-4ea4-8f21-84a4c541b110/L%C3%A5neanbefaling_rentetilpasning+januar+2022.pdf?MOD=AJPERES&CVID=nKxATf-"),
    ("20220123125943", "https://www.jyskebank.dk/wps/wcm/connect/jfo/4068e940-81bd-4308-83d2-42b7f3485f80/L%C3%A5neanbefaling_rentetilpasning+april+2022.pdf?MOD=AJPERES&CVID=nRS8tFd"),
    ("20221004024318", "https://www.jyskebank.dk/wps/wcm/connect/jfo/08e6c8db-dc44-4a0a-bb80-50ec066c6721/boliglaansanbefaling-rentetilpasning-januar-2023.pdf?MOD=AJPERES&CVID=odqrHGd"),
    ("20221129051953", "https://www.jyskebank.dk/wps/wcm/connect/jfo/08e6c8db-dc44-4a0a-bb80-50ec066c6721/boliglaansanbefaling-rentetilpasning-april-2023.pdf.pdf?MOD=AJPERES&CVID=oiuDjaY"),
    ("20230806173902", "https://www.jyskebank.dk/wps/wcm/connect/jfo/1f821ea4-27c7-40d3-abad-8eaf4b5d8cf8/L%C3%A5nanbefaling_rentetilpasning+oktober+2023.pdf?MOD=AJPERES&CVID=oAA.O8L"),
    # Generelle notater uden renteprognose - de giver ingen prognose, men
    # ligger her fordi de daekker kvartaler hvor der ikke findes en tabel.
    ("20221004024318", "https://www.jyskebank.dk/wps/wcm/connect/jfo/874a1f89-9a6f-495f-a30f-08efa9dec6d6/boliglaansanbefaling-generel.pdf?MOD=AJPERES&CVID=odqsP3P"),
    ("20221129033019", "https://www.jyskebank.dk/wps/wcm/connect/jfo/874a1f89-9a6f-495f-a30f-08efa9dec6d6/boliglaansanbefaling-generel.pdf?MOD=AJPERES&CVID=oivDzvv"),
    ("20230208050202", "https://www.jyskebank.dk/wps/wcm/connect/jfo/874a1f89-9a6f-495f-a30f-08efa9dec6d6/boliglaansanbefaling-generel.pdf?MOD=AJPERES&CVID=omwOcjE"),
    # Tabelformatet (2024-). Q1 2024 ligger allerede i repoet som bl-2024-01-04.
    ("20240221075400", "https://www.jyskebank.dk/media/api/content/mediafiles/a0tjabgy/boliglaansanbefaling-1-kvartal-2024.pdf"),
    ("20241113192548", "https://www.jyskebank.dk/pdf/qqcnz2ut/boliglaansanbefaling-q4-2024-opdateret-1.pdf"),
    ("20241113181737", "https://www.jyskebank.dk/pdf/utfeizh1/laaneanbefaling-rentetilpasning-april-2025-privat.pdf"),
    ("20250419013256", "https://www.jyskebank.dk/pdf/wcm/00aec6b5-8b55-40ad-ba7b-f91c1edc7aee/forventning-til-rentetilpasning.pdf?MOD=AJPERES"),
    ("20250707230414", "https://www.jyskebank.dk/pdf/utfeizh1/forventning-til-kommende-rentetilpasning.pdf"),
]

FACIT_PATH = ROOT / "data" / "banks" / BANK_ID / "facit.json"

# Post-auktion-opgoerelserne "Resultat af rentetilpasning pr. 1. <maaned>"
# oplyser de kontantlånsrenter kunderne faktisk fik ved hver refinansiering.
# De er facit for prognoserne ovenfor, og de tilfoejes kun for perioden foer
# bankens egne observationer (se EARLIEST_OWN_FACIT).
RESULT_URLS = [
    ("20211206060046", "https://www.jyskebank.dk/media/api/content/mediafiles/vazehkgw/resultat-rentetilpasning-oktober-2021.pdf/"),
    ("20211202042835", "https://www.jyskebank.dk/media/api/content/mediafiles/uejdnkdt/resultat-rentetilpasning-januar-2022-ekstern.pdf/"),
    ("20250424005615", "https://www.jyskebank.dk/pdf/uejdnkdt/resultat-rentetilpasning-januar-2022-ekstern.pdf"),
    ("20250917015205", "https://www.jyskebank.dk/pdf/a3clk0nz/resultat-rentetilpasning-april-2022-ekstern.pdf"),
    ("20241005073131", "https://www.jyskebank.dk/media/api/content/mediafiles/xorhv1fq/resultat-rentetilpasning-oktober-2024.pdf"),
    ("20250707222815", "https://www.jyskebank.dk/pdf/002i3zce/resultat-rentetilpasning-april-2025_privat.pdf"),
    ("20260410192529", "https://www.jyskebank.dk/pdf/002i3zce/resultat-rentetilpasning-privat.pdf"),
]

# Fra denne dato har banken egne observationer (HTML-siden og
# Boliglånsanbefalingens "Lånerente pr."), og de bruges uaendret. Auktions-
# opgoerelserne supplerer altsaa kun perioden foer.
EARLIEST_OWN_FACIT = "2024-01-01"


def snap_dir() -> Path:
    d = ROOT / "data" / "banks" / BANK_ID / "snapshots"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _archive_get(ts: str, url: str):
    """Hent en arkiveret PDF. Internet Archive svarer jaevnligt 503/afbryder,
    saa der proeves flere gange med pause imellem."""
    import requests

    for attempt in range(4):
        try:
            r = requests.get(f"https://web.archive.org/web/{ts}id_/{url}",
                             headers=UA, timeout=180, allow_redirects=True)
            if r.status_code == 200 and r.content.startswith(b"%PDF"):
                return r.content
            return None
        except requests.RequestException:
            time.sleep(20 * (attempt + 1))
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    out_dir = snap_dir()
    saved = skipped = empty = failed = 0
    realized: dict[str, list] = {}
    for ts, url in ARCHIVE_URLS:
        name = urllib.parse.unquote(url.split("/")[-1].split("?")[0])[:52]
        if args.dry_run:
            print(f"  ville hente {ts} {name}")
            continue
        try:
            pdf = _archive_get(ts, url)
            if pdf is None:
                failed += 1
                print(f"  {ts} {name:54s} ikke PDF i arkivet")
                continue
            snap = jyske_anbefaling.parse_pdf_bytes(pdf, capture_ts=ts,
                                                    fallback_date="2020-01-01")
            if snap is None:
                # Tabelformatet (2024-) kraever pdfplumber
                try:
                    from banks import jyske_pdf
                    snap = jyske_pdf.parse_pdf(pdf, "pdf-boliglaansanbefaling",
                                               ts, "2020-01-01")
                except ImportError:
                    snap = None
            if snap is None:
                empty += 1
                print(f"  {ts} {name:54s} ingen prognosetabel")
                continue
            path = out_dir / f"bl-{snap['pub_date']}.json"
            if path.exists():
                old = json.loads(path.read_text(encoding="utf-8"))
                if (old.get("rows") or {}) == (snap.get("rows") or {}):
                    skipped += 1
                    print(f"  {ts} {name:54s} i forvejen gemt "
                          f"({snap['pub_date']})")
                    continue
            path.write_text(json.dumps(snap, ensure_ascii=False, indent=1),
                            encoding="utf-8")
            saved += 1
            for prod, obs in (snap.get("realized") or {}).items():
                realized.setdefault(prod, []).append(obs)
            print(f"  {ts} {name:54s} gemt bl-{snap['pub_date']}.json "
                  f"{sorted(snap['rows'])}")
        except Exception as e:
            failed += 1
            print(f"  {ts} {name:54s} FEJL {type(e).__name__}")
        time.sleep(1)

    # Facit fra figurernes realiserede renter og fra auktionsopgoerelserne
    # flettes ind i den eksterne facit-serie. Kilden for de foerste er de
    # *gemte* snapshots, saa den del kan koeres igen uden netvaerk - og
    # eksisterende serier (stat10, cibor3 fra Danmarks Statistik) maa ikke
    # overskrives.
    if not args.dry_run:
        facit = json.loads(FACIT_PATH.read_text(encoding="utf-8"))
        changed = False
        for path in sorted(out_dir.glob("*.json")):
            snap = json.loads(path.read_text(encoding="utf-8"))
            for prod, obs in (snap.get("realized") or {}).items():
                merged = {d: v for d, v in facit.get(prod, [])}
                if merged.get(obs[0]) == obs[1]:
                    continue
                merged[obs[0]] = obs[1]
                facit[prod] = sorted(merged.items())
                changed = True

        for ts, url in RESULT_URLS:
            try:
                pdf = _archive_get(ts, url)
            except Exception:
                pdf = None
            if pdf is None:
                failed += 1
                print(f"  {ts} {url.split('/')[-1][:44]:46s} ikke PDF i arkivet")
                continue
            res = jyske_resultat.parse_pdf_bytes(pdf)
            if res is None or res["date"] >= EARLIEST_OWN_FACIT:
                print(f"  {ts} {url.split('/')[-1][:44]:46s} "
                      f"{'uden tabel' if res is None else res['date'] + ' (har egne obs.)'}")
                continue
            for prod, v in res["rates"].items():
                merged = {d: val for d, val in facit.get(prod, [])}
                if merged.get(res["date"]) == v:
                    continue
                merged[res["date"]] = v
                facit[prod] = sorted(merged.items())
                changed = True
            print(f"  {ts} {url.split('/')[-1][:44]:46s} facit {res['date']}: "
                  + ", ".join(f"{k}={v:+.2f}" for k, v in sorted(res["rates"].items())))
            time.sleep(1)

        if changed:
            FACIT_PATH.write_text(
                json.dumps(facit, ensure_ascii=False, indent=1),
                encoding="utf-8")
        for prod in sorted(facit):
            series = facit[prod]
            print(f"  facit[{prod}]: {len(series)} observationer "
                  f"({series[0][0]} .. {series[-1][0]})")

    print(f"\nFaerdig: {saved} gemt, {skipped} i forvejen, {empty} uden tabel, "
          f"{failed} fejlede")
    return 0


if __name__ == "__main__":
    sys.exit(main())
