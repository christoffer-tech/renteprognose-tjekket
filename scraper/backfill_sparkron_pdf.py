"""Backfill Sparekassen Kronjyllands renteprognoser fra Investeringsmagasinet.

Magasinet indeholder en RENTEPROGNOSE-tabel (se banks/sparkron_pdf.py) og
dækker juli 2017 - marts 2019, altså før projektets hidtidige første prognose
(2022-11-11). PDF'erne ligger på en stabil sti og svarer HTTP 200.

Brug:
    python scraper/backfill_sparkron_pdf.py            # hent alle kendte udgaver
    python scraper/backfill_sparkron_pdf.py --dry-run  # vis hvad der ville blive hentet
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from banks import sparkron_pdf
from scrape import _save_if_new, snap_dir

BANK_ID = "sparkron"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    ok = skipped = failed = 0
    for month, expected in sparkron_pdf.MAGAZINE_MONTHS:
        url = sparkron_pdf.MAGAZINE_URL.format(month=month)
        name = f"magazine-{expected}.json"
        out = snap_dir(BANK_ID) / name
        if out.exists():
            print(f"[{month}] findes allerede ({name}) - springer over")
            skipped += 1
            continue
        if args.dry_run:
            print(f"[{month}] ville hente {url}")
            continue
        print(f"[{month}] henter {url}", flush=True)
        try:
            snap = sparkron_pdf.fetch_and_parse(
                url, source="magazine", capture_ts=None,
                fallback_date=expected)
        except Exception as e:
            print(f"[{month}] FEJL: {type(e).__name__}: {e}", flush=True)
            failed += 1
            continue
        if snap is None:
            print(f"[{month}] ingen RENTEPROGNOSE-tabel fundet", flush=True)
            failed += 1
            continue
        if snap["pub_date"] != expected:
            # Ikke en fejl i sig selv, men værd at se: så er filen skiftet ud.
            print(f"[{month}] ADVARSEL: pub_date={snap['pub_date']} "
                  f"(forventet {expected})", flush=True)
        snap["pdf_month"] = month
        _save_if_new(BANK_ID, snap, name)
        print(f"[{month}] pub={snap['pub_date']} "
              f"produkter={sorted(snap['rows'])}", flush=True)
        ok += 1

    print(f"\nFærdig: {ok} nye, {skipped} sprunget over, {failed} fejlede")
    return 1 if failed and not ok else 0


if __name__ == "__main__":
    sys.exit(main())
