"""Backfill + løbende snapshot af Jyskes "Boliglånsanbefaling"-notater.

To kilder:
  1) Wayback-kopien af Q1 2024-notatet — det eneste ældre notat der er bevaret.
  2) Den stabile /pdf/qqcnz2ut/boliglaansanbefaling.pdf, som altid giver den
     nyeste udgave. Den hentes ved den ugentlige opdatering, så serien vokser
     med én post pr. kvartal, ligesom live-snapshots af HTML-siden.

Brug:
    python scraper/backfill_jyske_pdf.py           # hent begge
    python scraper/backfill_jyske_pdf.py --dry-run
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from banks import jyske_pdf
from scrape import _save_if_new, snap_dir

BANK_ID = "jyske"


def _do(url: str, name: str, source: str, capture: str | None,
        fallback: str, dry: bool) -> bool:
    if (snap_dir(BANK_ID) / name).exists():
        print(f"[{name}] findes allerede - springer over")
        return True
    if dry:
        print(f"[{name}] ville hente {url[:96]}")
        return True
    try:
        snap = jyske_pdf.fetch_and_parse(url, source=source, capture_ts=capture,
                                         fallback_date=fallback)
    except Exception as e:
        print(f"[{name}] FEJL: {type(e).__name__}: {e}")
        return False
    if snap is None:
        print(f"[{name}] ingen 'Forventninger til realkreditrenten'-tabel "
              f"(notatet har den ikke i denne udgave)")
        return False
    print(f"[{name}] pub={snap['pub_date']} targets={snap['targets']} "
          f"produkter={sorted(snap['rows'])}")
    _save_if_new(BANK_ID, snap, name)
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    ok = 0
    # 1) Historisk: Q1 2024 fra arkivet
    if _do(jyske_pdf.Q1_2024_URL, f"bl-{jyske_pdf.Q1_2024_PUB}.json",
           "wayback", "20240221", jyske_pdf.Q1_2024_PUB, args.dry_run):
        ok += 1

    # 2) Nyeste udgave fra den stabile URL (løbende serie)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M")
    if _do(jyske_pdf.LIVE_URL, f"bl-live-{stamp}.json",
           "live-pdf", None, dt.date.today().isoformat(), args.dry_run):
        ok += 1

    print(f"\nFærdig: {ok} kilde(r) behandlet")
    return 0


if __name__ == "__main__":
    sys.exit(main())
