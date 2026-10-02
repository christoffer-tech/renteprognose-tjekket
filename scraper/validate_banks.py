# -*- coding: utf-8 -*-
"""Valider multi-bank datasæt: pub/capture-anomalier + overordnede metrics."""
import datetime as dt
import glob
import json

for bank, pattern in [
    ("nykredit", "data/snapshots/*.json"),
    ("nordea", "data/banks/nordea/snapshots/*.json"),
    ("sydbank", "data/banks/sydbank/snapshots/*.json"),
    ("jyske", "data/banks/jyske/snapshots/*.json"),
    ("rd", "data/banks/rd/snapshots/*.json"),
]:
    print("=" * 25, bank)
    for f in sorted(glob.glob(pattern)):
        s = json.load(open(f, encoding="utf-8"))
        if s.get("capture"):
            cap = f"{s['capture'][0:4]}-{s['capture'][4:6]}-{s['capture'][6:8]}"
            pub = s["pub_date"]
            delta = (dt.date.fromisoformat(cap) - dt.date.fromisoformat(pub)).days
            flag = "  <-- TJEK" if (delta < -1 or delta > 120) else ""
            if flag:
                print(f"  {f.split(chr(92))[-1]} cap={cap} pub={pub} delta={delta}d{flag}")

for bank, path in [
    ("nykredit", "data/dataset.json"),
    ("nordea", "data/banks/nordea/dataset.json"),
    ("sydbank", "data/banks/sydbank/dataset.json"),
    ("jyske", "data/banks/jyske/dataset.json"),
    ("rd", "data/banks/rd/dataset.json"),
]:
    d = json.load(open(path, encoding="utf-8"))
    o = d["overall"]
    print(f"{bank:10s} n={o['n']:4d} bias={o['bias']:+.3f} mae={o['mae']:.3f} "
          f"opt={o['opt_share']:.0%} hit={o.get('hit_rate')} "
          f"({d['meta']['first_pub']}..{d['meta']['last_pub']})")
