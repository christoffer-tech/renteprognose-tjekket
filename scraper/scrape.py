"""Orkestrering af bank-scrapere.

Brug:
    python scrape.py update [bank]    # hent live-side (default: alle banker)
    python scrape.py backfill [bank]  # historik via Wayback (default: alle)
    python scrape.py facit-rd         # RD's historiske FlexLån-renter

Nykredit-snapshots ligger i data/snapshots/ (legacy-sti, bruges af
data/dataset.json). Øvrige banker under data/banks/<bank>/snapshots/.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from banks import jyske, nordea, nykredit, rd, sydbank
from common import (BROWSER_HEADERS, ROOT, fetch, list_captures,
                    snapshot_fingerprint, wayback_url)

BANKS = {m.BANK_ID: m for m in (nykredit, nordea, sydbank, jyske, rd)}

BANK_HEADERS = {"sydbank": BROWSER_HEADERS}


def snap_dir(bank_id: str) -> Path:
    if bank_id == "nykredit":
        d = ROOT / "data" / "snapshots"
    else:
        d = ROOT / "data" / "banks" / bank_id / "snapshots"
    d.mkdir(parents=True, exist_ok=True)
    return d


def fetch_live(mod) -> str:
    return fetch(mod.PAGE_URL, headers=BANK_HEADERS.get(mod.BANK_ID))


def cmd_update(bank_ids: list[str]) -> None:
    for bank_id in bank_ids:
        mod = BANKS[bank_id]
        print(f"[{bank_id}] Henter live-side...", flush=True)
        try:
            html = fetch_live(mod)
        except RuntimeError as e:
            print(f"[{bank_id}] FEJL: {e}", flush=True)
            continue
        today = dt.date.today().isoformat()
        snap = mod.parse_snapshot(html, "live", None, today)
        if snap is None:
            print(f"[{bank_id}] FEJL: kunne ikke parse prognosetabellen", flush=True)
            continue
        print(f"[{bank_id}] pub={snap['pub_date']} produkter={sorted(snap['rows'])}",
              flush=True)
        d = snap_dir(bank_id)
        existing = sorted(d.glob("*.json"))
        if existing:
            latest = json.loads(existing[-1].read_text(encoding="utf-8"))
            if snapshot_fingerprint(latest) == snapshot_fingerprint(snap):
                print(f"[{bank_id}] ingen ændring - gemmer ikke.", flush=True)
                continue
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M")
        out = d / f"live-{stamp}.json"
        out.write_text(json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"[{bank_id}] gemt {out.name}", flush=True)


def cmd_backfill(bank_ids: list[str]) -> None:
    for bank_id in bank_ids:
        mod = BANKS[bank_id]
        try:
            captures = list_captures(mod.PAGE_URL)
        except Exception as e:
            print(f"[{bank_id}] FEJL ved CDX-opslag: {e}", flush=True)
            continue
        d = snap_dir(bank_id)
        new, skipped, failed = 0, 0, 0
        for cap in captures:
            ts = cap["timestamp"]
            out = d / f"{ts}.json"
            if out.exists():
                skipped += 1
                continue
            try:
                html = fetch(wayback_url(cap),
                             headers=BANK_HEADERS.get(bank_id))
            except RuntimeError:
                failed += 1
                continue
            fallback = f"{ts[0:4]}-{ts[4:6]}-{ts[6:8]}"
            snap = mod.parse_snapshot(html, "wayback", ts, fallback)
            if snap is None:
                print(f"[{bank_id}] {ts}: ingen tabel fundet", flush=True)
                failed += 1
                continue
            out.write_text(json.dumps(snap, ensure_ascii=False, indent=1),
                           encoding="utf-8")
            print(f"[{bank_id}] {ts}: pub={snap['pub_date']} "
                  f"produkter={len(snap['rows'])} OK", flush=True)
            new += 1
            time.sleep(1)
        print(f"[{bank_id}] færdig: {new} nye, {skipped} sprunget over, "
              f"{failed} fejlede", flush=True)


def cmd_facit_rd() -> None:
    print("[rd] Henter historiske FlexLån-renter...", flush=True)
    try:
        html = fetch(rd.FACIT_URL)
    except RuntimeError as e:
        print(f"[rd] FEJL: {e}", flush=True)
        return
    series = rd.parse_facit(html)
    total = sum(len(v) for v in series.values())
    print(f"[rd] {total} facit-punkter: " +
          ", ".join(f"{k}={len(v)}" for k, v in series.items()), flush=True)
    out = ROOT / "data" / "banks" / "rd" / "facit.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        old = json.loads(out.read_text(encoding="utf-8"))
        # flet: behold alt, overskriv aldrig historik med nyere scrape
        merged = {}
        for k in set(old) | set(series):
            by_date = {d: v for d, v in old.get(k, [])}
            for dd, vv in series.get(k, []):
                by_date.setdefault(dd, vv)
            merged[k] = sorted(by_date.items())
        series = merged
    out.write_text(json.dumps(series, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[rd] skrev {out}", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["update", "backfill", "facit-rd"])
    ap.add_argument("bank", nargs="?", choices=sorted(BANKS),
                    help="en enkelt bank (default: alle)")
    args = ap.parse_args()
    if args.cmd == "facit-rd":
        cmd_facit_rd()
        return
    bank_ids = [args.bank] if args.bank else sorted(BANKS)
    if args.cmd == "update":
        cmd_update(bank_ids)
    else:
        cmd_backfill(bank_ids)


if __name__ == "__main__":
    main()
