# -*- coding: utf-8 -*-
"""Validér multi-bank snapshots: pub/capture-anomalier + metrics pr. bank.

Kør fra vilkårlig mappe. Afslutter med exit-kode 1 hvis en check fejler, så
den kan bruges som gate i CI (supplerer validate.py med de rå snapshots).

Brug:
    python scraper/validate_banks.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import ROOT

BANKS = ("nykredit", "nordea", "sydbank", "jyske", "rd", "sparkron")

# En arkiveret optagelse kan ikke ligge før den publiceringsdato, banken selv
# angiver. Gør den det, er pub_date fejlparset (fx fordi parseren greb en
# datoandet steds på siden).
MIN_DELTA_DAYS = -1

# Den modsatte vej er derimod et normalt Wayback-fænomen: en side der ikke
# ændres, bliver arkiveret igen og igen med samme indhold, så capture-datoen
# kan ligge år efter publiceringsdatoen. Vi rapporterer det, men fejler ikke -
# dubletterne fjernes alligevel i build.py.
STALE_WARN_DAYS = 120

failures: list[str] = []


def fail(msg: str) -> None:
    failures.append(msg)
    print(f"  FEJL: {msg}")


def snap_dir(bank: str) -> Path:
    if bank == "nykredit":
        return ROOT / "data" / "snapshots"
    return ROOT / "data" / "banks" / bank / "snapshots"


def dataset_path(bank: str) -> Path:
    if bank == "nykredit":
        return ROOT / "data" / "dataset.json"
    return ROOT / "data" / "banks" / bank / "dataset.json"


def main() -> int:
    stale = 0
    for bank in BANKS:
        d = snap_dir(bank)
        files = sorted(d.glob("*.json"))
        print("=" * 25, bank, f"({len(files)} snapshots)")
        if not files:
            fail(f"[{bank}] ingen snapshots i {d.relative_to(ROOT)}")
            continue
        anomalies = 0
        for f in files:
            try:
                s = json.loads(f.read_text(encoding="utf-8"))
            except json.JSONDecodeError as e:
                fail(f"[{bank}] ugyldig JSON i {f.name}: {e}")
                continue
            pub = s.get("pub_date")
            if not pub:
                fail(f"[{bank}] {f.name} mangler pub_date")
                continue
            cap = s.get("capture")
            if not cap:
                continue
            try:
                cap_date = dt.date(int(cap[0:4]), int(cap[4:6]), int(cap[6:8]))
                pub_date = dt.date.fromisoformat(pub)
            except ValueError:
                fail(f"[{bank}] {f.name} har ugyldig capture/pub_date "
                     f"(capture={cap!r}, pub={pub!r})")
                continue
            delta = (cap_date - pub_date).days
            if delta < MIN_DELTA_DAYS:
                anomalies += 1
                print(f"  TJEK  {f.name} cap={cap_date} pub={pub} "
                      f"delta={delta}d  <-- pub_date ligger EFTER optagelsen")
            elif delta > STALE_WARN_DAYS:
                stale += 1
        if anomalies:
            fail(f"[{bank}] {anomalies} snapshot(s) hvor pub_date ligger efter "
                 f"capture-datoen - sandsynlig fejlparset dato")

    print()
    for bank in BANKS:
        path = dataset_path(bank)
        if not path.exists():
            fail(f"[{bank}] mangler {path.relative_to(ROOT)}")
            continue
        d = json.loads(path.read_text(encoding="utf-8"))
        o = d["overall"]
        if o["n"] == 0:
            fail(f"[{bank}] ingen punkter med facit")
            continue
        print(f"{bank:10s} n={o['n']:4d} bias={o['bias']:+.3f} "
              f"mae={o['mae']:.3f} opt={o['opt_share']:.0%} "
              f"hit={o.get('hit_rate')} "
              f"({d['meta']['first_pub']}..{d['meta']['last_pub']})")

    if failures:
        print()
        print(f"SNAPSHOT-VALIDERING FEJLEDE: {len(failures)} problem(er)")
        for f in failures:
            print(f"  - {f}")
        return 1
    print()
    if stale:
        print(f"Bemærk: {stale} snapshot(s) er genarkiveringer af en uændret "
              f"side (capture langt efter pub_date). De fjernes som dubletter "
              f"i build.py.")
    print("SNAPSHOT-VALIDERING OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
