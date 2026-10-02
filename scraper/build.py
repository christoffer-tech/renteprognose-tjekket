"""Byg data/dataset.json ud fra snapshots i data/snapshots/.

For hver prognose (snapshot S, produkt P, måldato T) findes facit som
'Aktuelt'-værdien fra det snapshot hvis pub_date ligger tættest på T
(samme rentedefinitioner, typisk <= 1 måneds forskydning).

Fejl = facit - prognose. Positiv fejl = renten blev højere end forudsagt
= prognosen var for optimistisk (set fra låntagers synspunkt).

Brug:
    python build.py
"""
from __future__ import annotations

import datetime as dt
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SNAP_DIR = ROOT / "data" / "snapshots"
DATA_DIR = ROOT / "data"

PRODUCT_LABELS = {
    "cita3": "CITA3",
    "cita6": "CITA6",
    "fkort": "F-kort",
    "f1": "F1",
    "f3": "F3",
    "f5": "F5",
    "fast20": "Fast rente 20 år",
    "fast30": "Fast rente 30 år",
}
PRODUCT_ORDER = ["cita3", "cita6", "fkort", "f1", "f3", "f5", "fast20", "fast30"]

# max afstand (dage) mellem måldato og nærmeste facit-snapshot før facit droppes
MAX_FACIT_GAP_DAYS = 60


def load_snapshots() -> list[dict]:
    snaps = []
    for f in sorted(SNAP_DIR.glob("*.json")):
        try:
            snaps.append(json.loads(f.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError) as e:
            print(f"ADVARSEL: springer {f.name} over ({e})")
    snaps.sort(key=lambda s: (s.get("pub_date") or "", s.get("capture") or ""))
    # fjern dubletter med identisk indhold (behold tidligste capture)
    seen: set[str] = set()
    unique = []
    for s in snaps:
        core = {k: v for k, v in s.items() if k not in ("source", "capture")}
        fp = json.dumps(core, sort_keys=True)
        if fp in seen:
            continue
        seen.add(fp)
        unique.append(s)
    if len(unique) != len(snaps):
        print(f"{len(snaps) - len(unique)} dublet-snapshots fjernet")
    return unique


def horizon_bucket(pub: str, target: str) -> str:
    days = (dt.date.fromisoformat(target) - dt.date.fromisoformat(pub)).days
    q = int(round(days / 91.31))
    return {0: "0M", 1: "3M", 2: "6M", 3: "9M"}.get(q, "12M")


def summarize(errors: list[float]) -> dict:
    n = len(errors)
    if n == 0:
        return {"n": 0, "bias": None, "mae": None, "rmse": None, "opt_share": None}
    bias = sum(errors) / n
    mae = sum(abs(e) for e in errors) / n
    rmse = (sum(e * e for e in errors) / n) ** 0.5
    opt = sum(1 for e in errors if e > 0) / n
    return {"n": n, "bias": round(bias, 3), "mae": round(mae, 3),
            "rmse": round(rmse, 3), "opt_share": round(opt, 3)}


def main() -> None:
    snaps = load_snapshots()
    print(f"{len(snaps)} snapshots indlæst")
    if not snaps:
        raise SystemExit("Ingen snapshots - kør scrape.py først")

    def obs_of(s: dict) -> str:
        if s.get("obs_date"):
            return s["obs_date"]
        cap = s.get("capture")
        if cap:
            return f"{cap[0:4]}-{cap[4:6]}-{cap[6:8]}"
        return s["pub_date"]

    # facit-serier: pr. produkt liste af (obs-dato, aktuelt).
    # obs-dato = hvornår 'Aktuelt' faktisk blev observeret (capture-dato),
    # ikke prognosens publiceringsdato.
    facit: dict[str, list[tuple[str, float]]] = {p: [] for p in PRODUCT_ORDER}
    for s in snaps:
        for p, row in s.get("rows", {}).items():
            if p in facit and row.get("aktuelt") is not None:
                facit[p].append((obs_of(s), row["aktuelt"]))
    for p in facit:
        facit[p].sort()
        facit[p] = list(dict.fromkeys(facit[p]))  # fjern eksakte dubletter

    points: list[dict] = []
    for s in snaps:
        pub = s["pub_date"]
        # filtrer evt. None-måldatoer fra (ældre snapshots) så positioner flugter
        tgts = [t for t in (s.get("targets") or []) if t]
        for i, target in enumerate(tgts):
            for p, row in s.get("rows", {}).items():
                if p not in PRODUCT_ORDER:
                    continue
                fc_list = row.get("forecasts") or []
                fc = fc_list[i] if i < len(fc_list) else None
                if fc is None:
                    continue
                # find nærmeste facit
                best = None
                for fdate, fval in facit[p]:
                    gap = abs((dt.date.fromisoformat(fdate)
                               - dt.date.fromisoformat(target)).days)
                    if best is None or gap < best[0]:
                        best = (gap, fdate, fval)
                act = act_date = err = None
                gap_days = best[0] if best else None
                if best and best[0] <= MAX_FACIT_GAP_DAYS:
                    _, act_date, act = best
                    err = round(act - fc, 3)
                points.append({
                    "p": p, "pub": pub, "target": target,
                    "h": horizon_bucket(pub, target),
                    "fc": fc, "act": act, "act_date": act_date,
                    "err": err, "gap_days": gap_days,
                })

    points.sort(key=lambda x: (x["p"], x["pub"], x["target"]))

    # metrics pr. produkt x horisont + samlet
    metrics: dict[str, dict[str, dict]] = {}
    for p in PRODUCT_ORDER:
        metrics[p] = {}
        for h in ["3M", "6M", "9M", "12M", "alle"]:
            errs = [x["err"] for x in points
                    if x["p"] == p and x["err"] is not None
                    and (h == "alle" or x["h"] == h)]
            metrics[p][h] = summarize(errs)
    overall = summarize([x["err"] for x in points if x["err"] is not None])

    first_pub = min(s["pub_date"] for s in snaps)
    last_pub = max(s["pub_date"] for s in snaps)

    # ankre: snapshot'ets egen Aktuelt-værdi pr. publiceringsdato (startpunkt for vintage-linjer)
    anchors: dict[str, list[list]] = {p: [] for p in PRODUCT_ORDER}
    for s in snaps:
        for p, row in s.get("rows", {}).items():
            if p in anchors and row.get("aktuelt") is not None:
                if not anchors[p] or anchors[p][-1][0] != s["pub_date"]:
                    anchors[p].append([s["pub_date"], row["aktuelt"]])

    dataset = {
        "meta": {
            "generated": dt.datetime.now().isoformat(timespec="seconds"),
            "n_snapshots": len(snaps),
            "n_points": len(points),
            "n_with_facit": sum(1 for x in points if x["err"] is not None),
            "first_pub": first_pub,
            "last_pub": last_pub,
            "method": ("Facit pr. måldato er 'Aktuelt'-værdien fra det snapshot, "
                       "hvor observationen ligger tættest på måldatoen "
                       "(samme rentedefinitioner). Fejl = facit - prognose; "
                       "positiv fejl = for optimistisk prognose."),
        },
        "labels": PRODUCT_LABELS,
        "order": [p for p in PRODUCT_ORDER if any(x["p"] == p for x in points)],
        "actuals": {p: [[d, v] for d, v in facit[p]] for p in PRODUCT_ORDER},
        "anchors": anchors,
        "points": points,
        "metrics": metrics,
        "overall": overall,
    }
    out = DATA_DIR / "dataset.json"
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
                print("Ingen ændringer i datasættet - dataset.json opdateres ikke")
                return
    out.write_text(json.dumps(dataset, ensure_ascii=False), encoding="utf-8")
    print(f"Skrev {out} ({len(points)} punkter, "
          f"{sum(1 for x in points if x['err'] is not None)} med facit)")


if __name__ == "__main__":
    main()
