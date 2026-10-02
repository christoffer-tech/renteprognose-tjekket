"""Byg data/comparison.json: bank-sammenligning på fællesmængden.

Kanoniske sammenligningsprodukter (samme markedsrente på tværs af banker):
- F3, F5  : alle 5 banker
- F1      : alle undtagen Sydbank
- FKORT   : Nykredit F-kort, RD FlexKort, Sydbank F-kort
            (Nordeas 'Kort Rente' er CITA6 uden tillæg -> CITA6 i stedet)
- CITA3   : Nykredit, Sydbank (Cita3M)
- CIBOR3  : Nordea (BoligPuls), Sydbank (Cibor3M)
- FAST30  : Nykredit (4 % eff.), Nordea (4 % eff.), Sydbank (30-årig)

Udeladt af rangering: Jyske fast30kupon (flad kupon, ikke prognose),
Jyske Frihed, Nordea CIBOR6/erhverv, Sydbank stat10, Nykredit CITA/CITA6
(vises i bankens eget dashboard, men indgår ikke i den fælles rangliste).

Jyskes F-renter er ekskl. kursfradrag. Til NIVEAU-sammenligning lægges
fradraget til (+0,3 F1 / +0,2 F3/F5). Fejl (facit - prognose) er upåvirket,
da både prognose og facit er ekskl. fradrag.

Rangering: pr. (produkt, horisont)-celle med >= 2 banker og >= 3 punkter
pr. bank rangeres bankerne efter MAE. Mesterskab = middelrang (min. 3
celler for at deltage). Herudover samlet bias/optimismeandel over F3+F5.

Brug:
    python compare.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import ROOT

BANK_LABELS = {
    "nykredit": "Nykredit",
    "nordea": "Nordea",
    "sydbank": "Sydbank",
    "jyske": "Jyske Bank",
    "rd": "Realkredit Danmark",
    "sparkron": "Sparekassen Kronjylland",
}
BANK_COLORS = {
    "nykredit": "#1f5fa8",
    "nordea": "#00b2e3",
    "sydbank": "#d62728",
    "jyske": "#2ca02c",
    "rd": "#9467bd",
    "sparkron": "#ff7f0e",
}

# bank-produkt -> kanonisk sammenligningsprodukt
CANONICAL_MAP = {
    "nykredit": {"f1": "F1", "f3": "F3", "f5": "F5", "fkort": "FKORT",
                 "cita3": "CITA3", "fast30": "FAST30"},
    "nordea": {"f1": "F1", "f3": "F3", "f5": "F5", "cita6": "CITA6",
               "cibor3": "CIBOR3", "fast30": "FAST30"},
    "sydbank": {"f3": "F3", "f5": "F5", "fkort": "FKORT", "cita3": "CITA3",
                "cibor3": "CIBOR3", "fast30": "FAST30"},
    "jyske": {"f1": "F1", "f3": "F3", "f5": "F5"},
    "rd": {"f1": "F1", "f3": "F3", "f5": "F5", "fkort": "FKORT"},
    "sparkron": {"f1": "F1", "f3": "F3", "f5": "F5", "fkort": "FKORT",
                 "cita3": "CITA3", "fast30": "FAST30"},
}
CANONICAL_LABELS = {
    "F1": "F1", "F3": "F3", "F5": "F5", "FKORT": "F-kort-type",
    "CITA3": "CITA3", "CITA6": "CITA6", "CIBOR3": "CIBOR3", "FAST30": "Fast 30 år",
}

# niveau-justering til head-to-head-grafer (Jyske ekskl. kursfradrag)
LEVEL_ADJUST = {"jyske": {"f1": 0.3, "f3": 0.2, "f5": 0.2}}

MIN_N_PER_CELL = 3
MIN_CELLS_CHAMPIONSHIP = 3
HORIZONS = ["3M", "6M", "9M", "12M"]


def load(bank: str) -> dict:
    p = ROOT / "data" / "banks" / bank / "dataset.json" \
        if bank != "nykredit" else ROOT / "data" / "dataset.json"
    return json.loads(p.read_text(encoding="utf-8"))


def summarize(errors: list[float]) -> dict:
    n = len(errors)
    if n == 0:
        return {"n": 0, "bias": None, "mae": None, "rmse": None, "opt_share": None}
    return {"n": n,
            "bias": round(sum(errors) / n, 3),
            "mae": round(sum(abs(e) for e in errors) / n, 3),
            "rmse": round((sum(e * e for e in errors) / n) ** 0.5, 3),
            "opt_share": round(sum(1 for e in errors if e > 0) / n, 3)}


def main() -> None:
    datasets = {b: load(b) for b in BANK_LABELS}

    # saml fejl pr. (kanonisk produkt, horisont, bank)
    errs: dict[tuple[str, str, str], list[float]] = {}
    for bank, ds in datasets.items():
        mapping = CANONICAL_MAP[bank]
        for pt in ds["points"]:
            if pt["err"] is None or pt["p"] not in mapping:
                continue
            if pt["h"] not in HORIZONS:
                continue
            key = (mapping[pt["p"]], pt["h"], bank)
            errs.setdefault(key, []).append(pt["err"])

    cells = []
    by_cell: dict[tuple[str, str], dict[str, list[float]]] = {}
    for (prod, h, bank), e in errs.items():
        by_cell.setdefault((prod, h), {})[bank] = e

    rank_points: dict[str, list[float]] = {b: [] for b in BANK_LABELS}
    for (prod, h), per_bank in sorted(by_cell.items()):
        eligible = {b: e for b, e in per_bank.items() if len(e) >= MIN_N_PER_CELL}
        if len(eligible) < 2:
            continue
        stats = {b: summarize(e) for b, e in eligible.items()}
        ranking = sorted(stats, key=lambda b: (stats[b]["mae"], stats[b]["bias"] is not None and abs(stats[b]["bias"])))
        for rank, b in enumerate(ranking, start=1):
            rank_points[b].append(rank)
        cells.append({
            "product": prod, "horizon": h,
            "banks": stats, "ranking": ranking,
        })

    championship = []
    for bank in BANK_LABELS:
        rp = rank_points[bank]
        if len(rp) >= MIN_CELLS_CHAMPIONSHIP:
            championship.append({
                "bank": bank,
                "mean_rank": round(sum(rp) / len(rp), 2),
                "cells": len(rp),
                "wins": sum(1 for r in rp if r == 1),
            })
    championship.sort(key=lambda c: (c["mean_rank"], -c["wins"]))

    # samlet optimisme over F3+F5 (alle horisonter <= 12M)
    bias_table = {}
    for bank, ds in datasets.items():
        mapping = CANONICAL_MAP[bank]
        e = [pt["err"] for pt in ds["points"]
             if pt["err"] is not None and mapping.get(pt["p"]) in ("F3", "F5")
             and pt["h"] in HORIZONS]
        pubs = [pt["pub"] for pt in ds["points"] if pt["err"] is not None]
        bias_table[bank] = {**summarize(e),
                            "period": [min(pubs), max(pubs)] if pubs else [None, None]}

    # RD interval hit-rate pr. horisont
    rd_hits = {}
    rds = datasets["rd"]
    for h in HORIZONS:
        hits = [pt["hit"] for pt in rds["points"]
                if pt["p"] in ("f1", "f3", "f5") and pt["h"] == h
                and pt["hit"] is not None]
        if hits:
            rd_hits[h] = {"n": len(hits),
                          "hit_rate": round(sum(1 for x in hits if x) / len(hits), 3)}

    # overall pr. bank (alle produkter/horisonter) - bruges til Skam-skammelen
    overall = {}
    for bank, ds in datasets.items():
        pubs = [pt["pub"] for pt in ds["points"] if pt["err"] is not None]
        overall[bank] = {**ds["overall"],
                         "period": [min(pubs), max(pubs)] if pubs else [None, None]}

    comparison = {
        "meta": {
            "generated": dt.datetime.now().isoformat(timespec="seconds"),
            "method": ("Rangering på fællesmængden: pr. (produkt, horisont)-celle "
                       "med >= 2 banker rangeres efter MAE. Mesterskab = middelrang. "
                       "Jyske-niveauer er +kursfradrag i grafer; fejl er upåvirkede. "
                       "RD-fejl er mod interval-midtpunkt."),
        },
        "banks": {b: {"label": BANK_LABELS[b], "color": BANK_COLORS[b]}
                  for b in BANK_LABELS},
        "canonical_labels": CANONICAL_LABELS,
        "mapping": {b: {bp: cp for bp, cp in m.items()} for b, m in CANONICAL_MAP.items()},
        "cells": cells,
        "championship": championship,
        "bias_table": bias_table,
        "overall": overall,
        "rd_hitrate": rd_hits,
        "level_adjust": LEVEL_ADJUST,
    }
    out = ROOT / "data" / "comparison.json"
    if out.exists():
        try:
            old = json.loads(out.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            old = None
        if old is not None:
            def comparable(d: dict) -> dict:
                meta = {k: v for k, v in d.get("meta", {}).items()
                        if k != "generated"}
                return {"meta": meta,
                        **{k: v for k, v in d.items() if k != "meta"}}
            if comparable(old) == comparable(comparison):
                print("Ingen ændringer - comparison.json opdateres ikke")
                return
    out.write_text(json.dumps(comparison, ensure_ascii=False), encoding="utf-8")
    print(f"Skrev {out}: {len(cells)} celler, "
          f"{len(championship)} banker i mesterskabet")
    for c in championship:
        print(f"  {BANK_LABELS[c['bank']]:18s} middelrang {c['mean_rank']} "
              f"({c['cells']} celler, {c['wins']} delsejre)")
    print("Bias F3+F5:")
    for b, s in bias_table.items():
        print(f"  {BANK_LABELS[b]:18s} n={s['n']:4d} bias={s['bias']:+.3f} "
              f"opt={s['opt_share']:.0%} {s['period'][0]}..{s['period'][1]}")


if __name__ == "__main__":
    main()
