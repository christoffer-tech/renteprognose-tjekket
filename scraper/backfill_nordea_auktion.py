"""Backfill Nordea auktions-prognoser (sitemap-discovery + live-download)."""
import datetime as dt
import hashlib
import json
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))

from banks import nordea_auktion
from common import ROOT

H = {"User-Agent": "Mozilla/5.0 renteprognose-tracker (research project)"}

d = ROOT / "data" / "banks" / "nordea" / "snapshots"
d.mkdir(parents=True, exist_ok=True)

try:
    sm = requests.get(nordea_auktion.SITEMAP_URL, headers=H, timeout=90).text
    urls = nordea_auktion.discover_urls(sm)
    print(f"[nordea-auktion] {len(urls)} artikler i sitemap", flush=True)
except Exception as e:
    print(f"[nordea-auktion] sitemap-FEJL: {e} - bruger kendte URL'er", flush=True)
    urls = []
for u in nordea_auktion.ARTICLE_URLS:
    if u not in urls:
        urls.append(u)

new, skipped, failed = 0, 0, 0
for url in sorted(urls):
    slug = hashlib.sha1(url.encode()).hexdigest()[:8]
    existing = sorted(d.glob(f"auktion-*-{slug}.json"))
    if existing:
        print(f"[nordea-auktion] {url[42:80]}...: findes allerede", flush=True)
        skipped += 1
        continue
    try:
        r = requests.get(url, headers=H, timeout=60)
        r.raise_for_status()
    except Exception as e:
        print(f"[nordea-auktion] {url}: download-FEJL {e}", flush=True)
        failed += 1
        continue
    snap = nordea_auktion.parse_article(r.text, url, "live-auktion", None,
                                        dt.date.today().isoformat())
    if snap is None:
        print(f"[nordea-auktion] {url}: kunne ikke parse", flush=True)
        failed += 1
        continue
    # 'rente i dag' er observeret ved publicering (facit i build.py)
    snap["obs_date"] = snap["pub_date"]
    out = d / f"auktion-{snap['pub_date']}-{slug}.json"
    out.write_text(json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[nordea-auktion] pub={snap['pub_date']} target={snap['targets']} "
          f"produkter={sorted(snap['rows'])} OK", flush=True)
    new += 1
    time.sleep(1)
print(f"færdig: {new} nye, {skipped} sprunget over, {failed} fejlede", flush=True)
