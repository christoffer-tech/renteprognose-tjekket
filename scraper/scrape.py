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
import hashlib
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from banks import jyske, nordea, nykredit, rd, sparkron, sydbank
from banks import nordea_auktion, sydbank_pdf, sydbank_refin
from common import (BROWSER_HEADERS, ROOT, fetch, list_captures,
                    snapshot_fingerprint, wayback_url)

BANKS = {m.BANK_ID: m for m in (nykredit, nordea, sydbank, jyske, rd, sparkron)}

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
        # sammenlign kun mod nyeste live-snapshot fra hovedtabellen
        # (pdf-/auktion-/refin-filer har deres eget dublettjek i _save_if_new)
        existing = sorted(d.glob("live-*.json"))
        if existing:
            latest = json.loads(existing[-1].read_text(encoding="utf-8"))
            if snapshot_fingerprint(latest) == snapshot_fingerprint(snap):
                print(f"[{bank_id}] ingen ændring - gemmer ikke.", flush=True)
                cmd_update_extra(bank_id, html if bank_id == "sydbank" else None)
                continue
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M")
        out = d / f"live-{stamp}.json"
        out.write_text(json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"[{bank_id}] gemt {out.name}", flush=True)
        cmd_update_extra(bank_id, html if bank_id == "sydbank" else None)


def _save_if_new(bank_id: str, snap: dict, filename: str) -> None:
    """Gem snapshot hvis ingen eksisterende fil har samme fingerprint."""
    d = snap_dir(bank_id)
    for f in sorted(d.glob("*.json")):
        try:
            old = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if snapshot_fingerprint(old) == snapshot_fingerprint(snap):
            print(f"[{bank_id}] {filename}: ingen ændring - gemmer ikke.",
                  flush=True)
            return
    out = d / filename
    out.write_text(json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[{bank_id}] gemt {out.name}", flush=True)


def cmd_update_extra(bank_id: str, sydbank_html: str | None = None) -> None:
    """Live-kilder ud over hovedtabellen (PDF/auktionsartikler). Fejl her
    maa aldrig vaelte den ordinaere update - alt er best-effort."""
    import requests
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M")
    today = dt.date.today().isoformat()
    headers = {"User-Agent": "Mozilla/5.0 renteprognose-tracker (research project)"}

    if bank_id == "sydbank":
        # 1) maanedens renteforventnings-PDF ('Grundlag for renteforventninger')
        try:
            html = sydbank_html or fetch(sydbank.PAGE_URL, headers=BROWSER_HEADERS)
            pdf_url = sydbank_pdf.latest_pdf_url(html)
            if pdf_url:
                import re as _re
                m = _re.search(r"ID=([0-9]+-[0-9]+)", pdf_url)
                tag = m.group(1) if m else stamp
                if not (snap_dir("sydbank") / f"pdf-{tag}.json").exists():
                    r = requests.get(pdf_url, headers=headers, timeout=90)
                    r.raise_for_status()
                    if r.content.startswith(b"%PDF"):
                        snap = sydbank_pdf.parse_pdf(r.content, "live-pdf", None, today)
                        if snap is not None:
                            snap["pdf_id"] = tag
                            snap["obs_date"] = snap["pub_date"]
                            _save_if_new("sydbank", snap, f"pdf-{tag}.json")
        except Exception as e:
            print(f"[sydbank] PDF-update sprunget over ({e})", flush=True)
        # 2) refinansierings-artiklen (kvartalsvis F1/F3/F5-prognose)
        try:
            html = fetch(sydbank_refin.PAGE_URL, headers=BROWSER_HEADERS)
            snap = sydbank_refin.parse_article(html, "live", None, today)
            if snap is not None:
                _save_if_new("sydbank", snap, f"refin-live-{stamp}.json")
        except Exception as e:
            print(f"[sydbank] refin-update sprunget over ({e})", flush=True)

    if bank_id == "nordea":
        # auktions-prognoser (3 stk/aar) via sitemap-discovery
        try:
            sm = requests.get(nordea_auktion.SITEMAP_URL, headers=headers,
                              timeout=90).text
            urls = nordea_auktion.discover_urls(sm)
        except Exception as e:
            print(f"[nordea] sitemap sprunget over ({e})", flush=True)
            urls = []
        for u in nordea_auktion.ARTICLE_URLS:
            if u not in urls:
                urls.append(u)
        n_new = 0
        for url in sorted(urls):
            try:
                slug = hashlib.sha1(url.encode()).hexdigest()[:8]
                if list(snap_dir("nordea").glob(f"auktion-*-{slug}.json")):
                    continue
                r = requests.get(url, headers=headers, timeout=60)
                r.raise_for_status()
                snap = nordea_auktion.parse_article(r.text, url, "live-auktion",
                                                   None, today)
                if snap is None:
                    continue
                snap["obs_date"] = snap["pub_date"]
                _save_if_new("nordea", snap,
                             f"auktion-{snap['pub_date']}-{slug}.json")
                n_new += 1
            except Exception as e:
                print(f"[nordea] {url[:60]}... sprunget over ({e})", flush=True)
                continue
        print(f"[nordea] auktion: {len(urls)} artikler tjekket, {n_new} nye",
              flush=True)


def page_urls(mod) -> list[str]:
    """Prognosesiden + eventuelle alternativer (spejle-/arkivsider)."""
    return [mod.PAGE_URL, *getattr(mod, "ALT_URLS", [])]


def snap_name(page_url: str, cap: dict, with_digest: bool = False) -> str:
    """Filnavn = capture-ts, suffiks hvis capture ikke er fra PAGE_URL."""
    def norm(u: str) -> str:
        return re.sub(r"^https?://(www\.)?", "", u.split("?")[0]).rstrip("/")

    if norm(cap.get("original", "")) == norm(page_url):
        base = f"{cap['timestamp']}"
    else:
        slug = hashlib.sha1(cap.get("original", "").encode()).hexdigest()[:6]
        base = f"{cap['timestamp']}-{slug}"
    if with_digest and cap.get("digest"):
        base += f"-{cap['digest'][:6].lower()}"
    return base + ".json"


def cmd_backfill(bank_ids: list[str], since: str = "2015",
                   collapse: str | None = "digest") -> None:
    for bank_id in bank_ids:
        mod = BANKS[bank_id]
        d = snap_dir(bank_id)
        new, skipped, failed = 0, 0, 0
        for page_url in page_urls(mod):
            try:
                captures = list_captures(page_url, since=since,
                                         collapse=collapse)
            except Exception as e:
                print(f"[{bank_id}] {page_url} FEJL ved CDX-opslag: {e}", flush=True)
                continue
            for cap in captures:
                ts = cap["timestamp"]
                out = d / snap_name(page_url, cap,
                                    with_digest=(collapse is None))
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
        # flet: behold alt, overskriv aldrig historik med nyere scrape.
        # NB: sorter nøgler for deterministisk output (set-rækkefølge er
        # ikke stabil på tværs af kørsler og gav ellers tomme diff-commits).
        merged = {}
        for k in sorted(set(old) | set(series)):
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
    ap.add_argument("--since", default="2015",
                    help="tidligste år for Wayback-backfill (default: 2015)")
    ap.add_argument("--full", action="store_true",
                    help="tag alle captures (uden digest-collapse) - "
                         "brugbart ved sjaeldent arkiverede sider")
    args = ap.parse_args()
    if args.cmd == "facit-rd":
        cmd_facit_rd()
        return
    bank_ids = [args.bank] if args.bank else sorted(BANKS)
    if args.cmd == "update":
        cmd_update(bank_ids)
    else:
        cmd_backfill(bank_ids, since=args.since,
                     collapse=None if args.full else "digest")


if __name__ == "__main__":
    main()
