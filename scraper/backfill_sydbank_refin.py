"""Backfill Sydbank refinansierings-artikler (live + Wayback)."""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from banks import sydbank_refin
from common import BROWSER_HEADERS, ROOT, fetch, list_captures, wayback_url

d = ROOT / "data" / "banks" / "sydbank" / "snapshots"
d.mkdir(parents=True, exist_ok=True)

new, skipped, failed = 0, 0, 0

# live
try:
    import datetime as _dt
    today = _dt.date.today().isoformat()
    html = fetch(sydbank_refin.PAGE_URL, headers=BROWSER_HEADERS)
    snap = sydbank_refin.parse_article(html, "live", None, today)
    if snap is not None:
        import datetime as dt
        out = d / f"refin-live-{dt.datetime.now().strftime('%Y%m%d-%H%M')}.json"
        # undgå dublet af samme prognose
        from common import snapshot_fingerprint
        dup = False
        for f in d.glob("refin-*.json"):
            old = json.loads(f.read_text(encoding="utf-8"))
            if snapshot_fingerprint(old) == snapshot_fingerprint(snap):
                dup = True
                break
        if dup:
            print("[sydbank-refin] live: ingen ændring", flush=True)
            skipped += 1
        else:
            out.write_text(json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"[sydbank-refin] live: pub={snap['pub_date']} target={snap['targets']} OK", flush=True)
            new += 1
    else:
        print("[sydbank-refin] live: kunne ikke parse", flush=True)
        failed += 1
except RuntimeError as e:
    print(f"[sydbank-refin] live FEJL: {e}", flush=True)
    failed += 1

# wayback
try:
    caps = list_captures(sydbank_refin.PAGE_URL, since="2015")
except Exception as e:
    print(f"[sydbank-refin] CDX-FEJL: {e}", flush=True)
    caps = []
for cap in caps:
    ts = cap["timestamp"]
    out = d / f"refin-{ts}.json"
    if out.exists():
        skipped += 1
        continue
    try:
        html = fetch(wayback_url(cap), headers=BROWSER_HEADERS)
    except RuntimeError:
        failed += 1
        continue
    snap = sydbank_refin.parse_article(html, "wayback", ts,
                                       f"{ts[0:4]}-{ts[4:6]}-{ts[6:8]}")
    if snap is None:
        print(f"[sydbank-refin] {ts}: ingen prognose fundet", flush=True)
        failed += 1
        continue
    out.write_text(json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[sydbank-refin] {ts}: pub={snap['pub_date']} target={snap['targets']} OK", flush=True)
    new += 1
    time.sleep(1)
print(f"færdig: {new} nye, {skipped} sprunget over, {failed} fejlede", flush=True)
