"""Byg datasæt pr. bank + legacy Nykredit-datasæt.

For hver prognose (snapshot S, produkt P, måldato T) findes facit som
'Aktuelt'-værdien fra nærmeste observation (samme rentedefinitioner).
RD's FlexLån bruger i stedet RD's egen historiske FlexLån-serie
(data/banks/rd/facit.json) med lineær interpolation mellem kvartalsvise
observationer.

Fejl = facit - prognose (for intervaller: mod midtpunktet). Positiv fejl =
for optimistisk (set fra låntagers synspunkt).

Brug:
    python build.py [bank|--all]   # default: alle banker
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import ROOT

PRODUCT_LABELS = {
    "cita3": "CITA3",
    "cita6": "CITA6",
    "cibor3": "CIBOR3",
    "cibor6": "CIBOR6",
    "fkort": "F-kort",
    "f1": "F1",
    "f3": "F3",
    "f5": "F5",
    "fast20": "Fast rente 20 år",
    "fast30": "Fast rente 30 år",
    "fast30kupon": "Fast 30 år (kupon)",
    "stat10": "10-årig statsrente",
    "frihed": "Jyske Frihed",
}
PRODUCT_ORDER = ["cita3", "cita6", "cibor3", "cibor6", "fkort", "f1", "f3",
                 "f5", "fast20", "fast30", "fast30kupon", "stat10", "frihed"]

HORIZONS = ["3M", "6M", "9M", "12M"]
MAX_FACIT_GAP_DAYS = 60
# RD: kvartalsvise facit-observationer (gaps paa 90/275 dage) -> interpolér.
# 140 dage dækker interpolation-vinduet (2 x 140 = 280 > 275); de aarlige
# observationer foer 2011 (365 dage) kan ikke naas med vilje - de ville kræve
# lineaær interpolation hen over et helt aar, hvilket er for groft.
RD_MAX_GAP_DAYS = 140

BANK_LABELS = {
    "nykredit": "Nykredit",
    "nordea": "Nordea",
    "sydbank": "Sydbank",
    "jyske": "Jyske Bank",
    "rd": "Realkredit Danmark",
    "sparkron": "Sparekassen Kronjylland",
}


def snap_dir(bank: str) -> Path:
    if bank == "nykredit":
        return ROOT / "data" / "snapshots"
    return ROOT / "data" / "banks" / bank / "snapshots"


def dataset_path(bank: str) -> Path:
    if bank == "nykredit":
        return ROOT / "data" / "dataset.json"
    p = ROOT / "data" / "banks" / bank / "dataset.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def load_snapshots(bank: str) -> list[dict]:
    d = snap_dir(bank)
    snaps = []
    for f in sorted(d.glob("*.json")):
        try:
            snaps.append(json.loads(f.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError) as e:
            print(f"[{bank}] ADVARSEL: springer {f.name} over ({e})")
    snaps.sort(key=lambda s: (s.get("pub_date") or "", s.get("capture") or ""))
    # Dublet: samme publiceringsdato og samme prognosticerede vaerdier. Obs-
    # datoen (capture-datoen) skal indgå i noeglen - ellers tæller 96 captures
    # af én og samme prognose som 96 uafhængige observationer. Ved dublet
    # beholder vi den seneste (dvs. capture med friskest 'Aktuelt').
    latest: dict[str, dict] = {}
    for s in snaps:
        core = {k: v for k, v in s.items() if k not in ("source", "capture", "obs_date")}
        latest[json.dumps(core, sort_keys=True)] = s
    if len(latest) != len(snaps):
        print(f"[{bank}] {len(snaps) - len(latest)} dublet-snapshots fjernet")
    return sorted(latest.values(), key=lambda s: (s["pub_date"], s.get("capture") or ""))


def horizon_bucket(pub: str, target: str) -> str:
    days = (dt.date.fromisoformat(target) - dt.date.fromisoformat(pub)).days
    q = int(round(days / 91.31))
    if q <= 0:
        return "0M"
    if q == 1:
        return "3M"
    if q == 2:
        return "6M"
    if q == 3:
        return "9M"
    if q == 4:
        return "12M"
    return f"{q * 3}M"


def summarize(errors: list[float], hits: list[bool] | None = None) -> dict:
    n = len(errors)
    out: dict = {"n": n, "bias": None, "mae": None, "rmse": None,
                 "opt_share": None, "pess_share": None, "hit_rate": None}
    if n == 0:
        return out
    out["bias"] = round(sum(errors) / n, 3)
    out["mae"] = round(sum(abs(e) for e in errors) / n, 3)
    out["rmse"] = round((sum(e * e for e in errors) / n) ** 0.5, 3)
    out["opt_share"] = round(sum(1 for e in errors if e > 0) / n, 3)
    out["pess_share"] = round(sum(1 for e in errors if e < 0) / n, 3)
    if hits:
        out["hit_rate"] = round(sum(1 for h in hits if h) / len(hits), 3)
        out["hit_n"] = len(hits)
    return out


def nearest_facit(series: list[tuple[str, float]], target: str,
                  interpolate: bool, max_gap: int):
    """Returner (værdi, obs_dato, gap_dage) eller (None, None, gap).

    Med interpolate=True interpoleres lineært mellem omsluttende
    observationer (hvis begge findes); ellers nærmeste inden for max_gap.
    """
    if not series:
        return None, None, None
    t = dt.date.fromisoformat(target)
    pts = [(dt.date.fromisoformat(d), v) for d, v in series]
    pts.sort()
    if interpolate:
        before = [(d, v) for d, v in pts if d <= t]
        after = [(d, v) for d, v in pts if d >= t]
        if before and after:
            d0, v0 = before[-1]
            d1, v1 = after[0]
            if d0 == d1:
                return v0, d0.isoformat(), 0
            if (d1 - d0).days <= max_gap * 2:
                w = (t - d0).days / (d1 - d0).days
                return round(v0 + w * (v1 - v0), 3), target, max(
                    (t - d0).days, (d1 - t).days)
    best = min(pts, key=lambda p: abs((p[0] - t).days))
    gap = abs((best[0] - t).days)
    if gap <= max_gap:
        return best[1], best[0].isoformat(), gap
    return None, None, gap


def build_bank(bank: str) -> dict:
    snaps = load_snapshots(bank)
    print(f"[{bank}] {len(snaps)} snapshots indlæst")
    if not snaps:
        raise SystemExit(f"[{bank}] ingen snapshots - kør scrape.py først")

    # evt. ekstern facit-serie (RD FlexLån)
    ext_facit: dict[str, list] = {}
    if bank == "rd":
        f = ROOT / "data" / "banks" / "rd" / "facit.json"
        if f.exists():
            ext_facit = json.loads(f.read_text(encoding="utf-8"))
            print(f"[{bank}] ekstern facit-serie: " +
                  ", ".join(f"{k}={len(v)}" for k, v in ext_facit.items()))

    def obs_of(s: dict) -> str:
        if s.get("obs_date"):
            return s["obs_date"]
        cap = s.get("capture")
        if cap:
            return f"{cap[0:4]}-{cap[4:6]}-{cap[6:8]}"
        return s["pub_date"]

    # facit-serier pr. produkt fra snapshot-Aktuelt
    facit: dict[str, list[tuple[str, float]]] = {p: [] for p in PRODUCT_ORDER}
    for s in snaps:
        for p, row in s.get("rows", {}).items():
            if p in facit and row.get("aktuelt") is not None:
                a = row["aktuelt"]
                if isinstance(a, dict):
                    a = round((a["lo"] + a["hi"]) / 2, 3)
                facit[p].append((obs_of(s), a))
    for p in facit:
        facit[p].sort()
        facit[p] = list(dict.fromkeys(facit[p]))
    # RD: erstat FlexLån-facit med den historiske serie
    for p, series in ext_facit.items():
        if p in facit and series:
            facit[p] = [(d, v) for d, v in series]

    interpolate = (bank == "rd")
    max_gap = RD_MAX_GAP_DAYS if bank == "rd" else MAX_FACIT_GAP_DAYS

    points: list[dict] = []
    for s in snaps:
        pub = s["pub_date"]
        snap_targets = [t for t in (s.get("targets") or []) if t]
        for p, row in s.get("rows", {}).items():
            if p not in PRODUCT_ORDER:
                continue
            tgts = [t for t in (row.get("targets") or []) if t] or snap_targets
            fc_list = row.get("forecasts") or []
            for i, target in enumerate(tgts):
                if i >= len(fc_list):
                    continue
                fc_raw = fc_list[i]
                if fc_raw is None:
                    continue
                if isinstance(fc_raw, dict):
                    lo, hi = fc_raw.get("lo"), fc_raw.get("hi")
                    if lo is None or hi is None:
                        continue
                    fc = round((lo + hi) / 2, 3)
                else:
                    lo = hi = None
                    fc = fc_raw
                act, act_date, gap_days = nearest_facit(
                    facit[p], target, interpolate, max_gap)
                err = hit = None
                if act is not None:
                    err = round(act - fc, 3)
                    if lo is not None:
                        hit = bool(lo <= act <= hi)
                points.append({
                    "p": p, "pub": pub, "target": target,
                    "h": horizon_bucket(pub, target),
                    "fc": fc, "fc_lo": lo, "fc_hi": hi,
                    "act": act, "act_date": act_date,
                    "err": err, "hit": hit, "gap_days": gap_days,
                })

    points.sort(key=lambda x: (x["p"], x["pub"], x["target"]))

    horizons = sorted({x["h"] for x in points})
    metrics: dict[str, dict[str, dict]] = {}
    for p in PRODUCT_ORDER:
        metrics[p] = {}
        for h in horizons + ["alle"]:
            sel = [x for x in points
                   if x["p"] == p and x["err"] is not None
                   and (h == "alle" or x["h"] == h)]
            metrics[p][h] = summarize(
                [x["err"] for x in sel],
                [x["hit"] for x in sel if x["hit"] is not None] or None)
    overall = summarize([x["err"] for x in points if x["err"] is not None],
                        [x["hit"] for x in points if x["hit"] is not None] or None)

    anchors: dict[str, list[list]] = {p: [] for p in PRODUCT_ORDER}
    for s in snaps:
        for p, row in s.get("rows", {}).items():
            if p in anchors and row.get("aktuelt") is not None:
                a = row["aktuelt"]
                if isinstance(a, dict):
                    a = round((a["lo"] + a["hi"]) / 2, 3)
                if not anchors[p] or anchors[p][-1][0] != s["pub_date"]:
                    anchors[p].append([s["pub_date"], a])

    dataset = {
        "meta": {
            "generated": dt.datetime.now().isoformat(timespec="seconds"),
            "bank": bank,
            "n_snapshots": len(snaps),
            "n_points": len(points),
            "n_with_facit": sum(1 for x in points if x["err"] is not None),
            "first_pub": min(s["pub_date"] for s in snaps),
            "last_pub": max(s["pub_date"] for s in snaps),
        },
        "labels": PRODUCT_LABELS,
        "order": [p for p in PRODUCT_ORDER if any(x["p"] == p for x in points)],
        "actuals": {p: [[d, v] for d, v in facit[p]] for p in PRODUCT_ORDER},
        "anchors": anchors,
        "points": points,
        "metrics": metrics,
        "overall": overall,
    }
    out = dataset_path(bank)
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
            if comparable(old) == comparable(dataset):
                print(f"[{bank}] ingen ændringer - dataset.json opdateres ikke")
                return dataset
    out.write_text(json.dumps(dataset, ensure_ascii=False), encoding="utf-8")
    print(f"[{bank}] skrev {out} ({len(points)} punkter, "
          f"{sum(1 for x in points if x['err'] is not None)} med facit)")
    return dataset


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("bank", nargs="?", default="all",
                    choices=["all"] + sorted(BANK_LABELS))
    args = ap.parse_args()
    banks = sorted(BANK_LABELS) if args.bank == "all" else [args.bank]
    for b in banks:
        build_bank(b)


if __name__ == "__main__":
    main()
