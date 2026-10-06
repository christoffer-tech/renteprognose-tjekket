"""Backfill Sydbanks "Økonomisk Oversigt" fra Wayback (2020-2022).

Serien indeholder en tabel "Renteniveau i procent, ultimo perioden" med
realiseret ultimoværdi + prognoser for de to kommende år (se
banks/sydbank_oversigt.py). Den dækker 2020-2022, hvor Sydbank ellers ikke har
data — hullet mellem den gamle HTML-side (slut 2019) og de månedlige
renteforventnings-PDF'er (2022-09 og frem).

De arkiverede PDF'er ligger som `?ID=`-links på markets.sydbank.dk. Ved
arkivets "miss" svarer det HTTP 200 med HTML, saa vi validerer paa %PDF.

Brug:
    python scraper/backfill_sydbank_oversigt.py
    python scraper/backfill_sydbank_oversigt.py --dry-run
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from banks import sydbank_oversigt
from scrape import _save_if_new, snap_dir

BANK_ID = "sydbank"

# (wayback-optagelse, publikations-ID, forventet publiceringsdato)
# Kun de aargangs-baserede tabeller tages med; 2023-06-udgaven skiftede til
# "3/6/12 mdr."-kolonner og udelades bevidst (se sydbank_oversigt.py).
EDITIONS = [
    ("20200517", "0043215-070181", "2020-05-04"),
    ("20210305", "0043215-076618", "2021-03-05"),
    ("20210625", "0043215-078857", "2021-06-25"),
    ("20220313", "0043215-094940", "2022-03-11"),
]

NAME = "oversigt-{pub}.json"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    ok = skipped = failed = 0
    for ts, pdf_id, expected in EDITIONS:
        name = NAME.format(pub=expected)
        if (snap_dir(BANK_ID) / name).exists():
            print(f"[{expected}] findes allerede - springer over")
            skipped += 1
            continue
        url = ("https://web.archive.org/web/{ts}id_/"
               "https://markets.sydbank.dk/PublicationsWebHandler/"
               "Default.aspx?ID={pid}").format(ts=ts, pid=pdf_id)
        if args.dry_run:
            print(f"[{expected}] ville hente {url}")
            continue
        print(f"[{expected}] henter optagelse {ts}", flush=True)
        try:
            snap = sydbank_oversigt.fetch_and_parse(
                url, source="wayback-oversigt", capture_ts=ts,
                fallback_date=expected)
        except Exception as e:
            print(f"[{expected}] FEJL: {type(e).__name__}: {e}", flush=True)
            failed += 1
            continue
        if snap is None:
            print(f"[{expected}] ingen aargangs-baseret rentetabel fundet",
                  flush=True)
            failed += 1
            continue
        if snap["pub_date"] != expected:
            print(f"[{expected}] ADVARSEL: pub_date={snap['pub_date']}",
                  flush=True)
        _save_if_new(BANK_ID, snap, name)
        print(f"[{expected}] pub={snap['pub_date']} "
              f"produkter={sorted(snap['rows'])} → {snap['targets']}",
              flush=True)
        ok += 1

    print(f"\nFærdig: {ok} nye, {skipped} sprunget over, {failed} fejlede")
    return 1 if failed and not ok else 0


if __name__ == "__main__":
    sys.exit(main())
