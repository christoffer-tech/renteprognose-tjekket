"""Backfill Sydbank renteforventnings-PDF'er (live-download + parse + snapshot)."""
import hashlib
import json
import sys
import time
from pathlib import Path
import datetime as dt

sys.path.insert(0, str(Path(__file__).resolve().parent))

from banks import sydbank_pdf
from common import ROOT, fetch

d = ROOT / "data" / "banks" / "sydbank" / "snapshots"
d.mkdir(parents=True, exist_ok=True)

new, skipped, failed = 0, 0, 0
for pid in sydbank_pdf.PDF_IDS:
    out = d / f"pdf-{pid}.json"
    if out.exists():
        print(f"[sydbank-pdf] {pid}: findes allerede", flush=True)
        skipped += 1
        continue
    url = sydbank_pdf.PDF_URL.format(id=pid)
    # PDF skal hentes som bytes (common.fetch returnerer tekst)
    import requests
    try:
        rr = requests.get(url, headers={"User-Agent": "Mozilla/5.0 renteprognose-tracker"},
                          timeout=60)
        rr.raise_for_status()
        pdf_bytes = rr.content
    except Exception as e:
        print(f"[sydbank-pdf] {pid}: download-FEJL {e}", flush=True)
        failed += 1
        continue
    if not pdf_bytes.startswith(b"%PDF"):
        print(f"[sydbank-pdf] {pid}: ikke en PDF ({len(pdf_bytes)} bytes)", flush=True)
        failed += 1
        continue
    snap = sydbank_pdf.parse_pdf(pdf_bytes, "live-pdf", None,
                                   dt.date.today().isoformat())
    if snap is None:
        print(f"[sydbank-pdf] {pid}: kunne ikke parse", flush=True)
        failed += 1
        continue
    snap["pdf_id"] = pid
    # P.t.-kolonnen er observeret ved publicering (ellers kan den ikke
    # bruges som facit i build.py)
    snap["obs_date"] = snap["pub_date"]
    out.write_text(json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[sydbank-pdf] {pid}: pub={snap['pub_date']} "
          f"produkter={sorted(snap['rows'])} OK", flush=True)
    new += 1
    time.sleep(1)
print(f"færdig: {new} nye, {skipped} sprunget over, {failed} fejlede", flush=True)
