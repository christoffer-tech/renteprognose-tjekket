# -*- coding: utf-8 -*-
"""Validér datasættene: strukturelle integritetschecks + metrics + spot-tjek.

Kør fra vilkårlig mappe. Afslutter med exit-kode 1 hvis en check fejler, så
den kan bruges som gate i CI (se .github/workflows/update.yml).

Brug:
    python scraper/validate.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import ROOT

# Datasæt i samme rækkefølge som siden viser dem.
DATASETS = [("nykredit", ROOT / "data" / "dataset.json")] + [
    (b, ROOT / "data" / "banks" / b / "dataset.json")
    for b in ("nordea", "sydbank", "jyske", "rd", "sparkron")
]

SANE_ERR = 5.0        # |fejl| i procentpoint - større er en parser-fejl
# RD's facit publiceres kun 1. jan og 1. apr (og interpoleres), så deres
# observationer ligger op til ~275 dage fra en måldato. Se build.RD_MAX_GAP_DAYS.
MAX_GAP = {"rd": 300}
DEFAULT_MAX_GAP = 200

failures: list[str] = []


def fail(msg: str) -> None:
    failures.append(msg)
    print(f"  FEJL: {msg}")


def check_dataset(bank: str, path: Path) -> dict | None:
    if not path.exists():
        fail(f"[{bank}] mangler: {path.relative_to(ROOT)}")
        return None
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        fail(f"[{bank}] ugyldig JSON i {path.relative_to(ROOT)}: {e}")
        return None

    pts = d.get("points") or []
    if not pts:
        fail(f"[{bank}] ingen punkter")
        return None

    # 1) Ingen gentagne prognoser. Samme (produkt, publiceringsdato, måldato)
    #    er ét udsagn; dubletter får metrics til at vægte enkeltprognoser
    #    tungere, alt efter hvor mange gange Wayback arkiverede dem.
    keys = [(p["p"], p["pub"], p["target"]) for p in pts]
    dupes = len(keys) - len(set(keys))
    if dupes:
        fail(f"[{bank}] {dupes} gentagne prognosepunkter "
             f"(samme produkt + publiceringsdato + måldato)")

    # 2) Påkrævede felter og sundhedstegn pr. punkt. Alle punkter tælles med,
    #    også når et enkelt er mistænkeligt, så meta-tallene kan afstemmes.
    required = ("p", "pub", "target", "h", "fc", "err")
    max_gap = MAX_GAP.get(bank, DEFAULT_MAX_GAP)
    n_err = 0
    suspicious: list[str] = []
    for i, p in enumerate(pts):
        missing = [k for k in required if k not in p]
        if missing:
            fail(f"[{bank}] punkt {i} mangler felter: {missing}")
            return None
        if p["target"] < p["pub"]:
            suspicious.append(f"{p['p']} pub={p['pub']} har måldato "
                              f"{p['target']} før publiceringsdatoen")
        if p["err"] is not None:
            n_err += 1
            if abs(p["err"]) > SANE_ERR:
                suspicious.append(f"{p['p']} pub={p['pub']} target={p['target']}"
                                  f" har fejl {p['err']:+.2f} pp (> {SANE_ERR})")
            if (p.get("gap_days") or 0) > max_gap:
                suspicious.append(f"{p['p']} pub={p['pub']} har facit-gap "
                                  f"{p['gap_days']} dage (> {max_gap})")
        fc, lo, hi = p.get("fc"), p.get("fc_lo"), p.get("fc_hi")
        if lo is not None and hi is not None and not (lo <= fc <= hi):
            suspicious.append(f"{p['p']} pub={p['pub']} har interval "
                              f"{lo}-{hi} der ikke omslutter midtpunktet {fc}")
    for msg in suspicious[:5]:
        fail(f"[{bank}] {msg}")
    if len(suspicious) > 5:
        fail(f"[{bank}] ... og {len(suspicious) - 5} flere mistænkelige punkter")

    # 3) Meta-tallene skal stemme med indholdet.
    meta = d.get("meta") or {}
    if meta.get("n_points") != len(pts):
        fail(f"[{bank}] meta.n_points={meta.get('n_points')} men "
             f"punkter={len(pts)}")
    if meta.get("n_with_facit") != n_err:
        fail(f"[{bank}] meta.n_with_facit={meta.get('n_with_facit')} men "
             f"punkter med facit={n_err}")

    # 4) Datasættet må ikke være tomt for den nyeste periode (scraper tavst i
    #    stykker). Vi tillader rigelig slæk - det fanger nedbrud, ikke orlov.
    last_pub = meta.get("last_pub")
    if last_pub:
        age = (dt.date.today() - dt.date.fromisoformat(last_pub)).days
        if age > 120:
            fail(f"[{bank}] nyeste prognose er {age} dage gammel "
                 f"({last_pub}) - opdateringen ser ud til at være stoppet")

    print(f"[{bank}] {len(pts)} punkter, {n_err} med facit, "
          f"sidste pub {last_pub}")
    return d


def check_comparison() -> None:
    path = ROOT / "data" / "comparison.json"
    if not path.exists():
        fail("mangler data/comparison.json - kør compare.py")
        return
    try:
        c = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        fail(f"ugyldig JSON i data/comparison.json: {e}")
        return

    banks = set(c.get("banks") or {})
    if not banks:
        fail("comparison.json har ingen banker")
        return
    for cell in c.get("cells") or []:
        if cell["ranking"] != sorted(
                cell["ranking"], key=lambda b: cell["banks"][b]["mae"]):
            fail(f"celle {cell['product']}/{cell['horizon']} er ikke "
                 f"rangeret efter MAE")
            break
        unknown = set(cell["banks"]) - banks
        if unknown:
            fail(f"celle {cell['product']}/{cell['horizon']} nævner ukendte "
                 f"banker: {sorted(unknown)}")
            break
    print(f"comparison.json: {len(c.get('cells') or [])} celler, "
          f"{len(c.get('championship') or [])} banker i mesterskabet")



# Et produkt skal kunne sammenlignes på tværs af banker. Ellers hører det ikke
# i datasættet: så peger den enkelte banks produktliste i sin egen retning.
MIN_COMPARABLE_BANKS = 2
MIN_POINTS_PER_BANK = 3      # samme graense som compare.MIN_N_PER_CELL


def check_comparable(datasets: dict) -> None:
    """Hvert produkt skal være evalueret af mindst to banker."""
    per_product: dict[str, list[tuple[str, int]]] = {}
    for bank, d in datasets.items():
        for p in d["order"]:
            m = d["metrics"][p].get("alle")
            n = m["n"] if m else 0
            per_product.setdefault(p, []).append((bank, n))

    for p, rows in sorted(per_product.items()):
        usable = [(b, n) for b, n in rows if n >= MIN_POINTS_PER_BANK]
        if len(usable) < MIN_COMPARABLE_BANKS:
            detail = ", ".join(f"{b}={n}" for b, n in sorted(rows))
            failures.append(
                f"produkt '{p}' kan ikke sammenlignes: kun {len(usable)} bank(er) "
                f"med >= {MIN_POINTS_PER_BANK} evaluerede prognoser ({detail})")


def main() -> int:
    print("Validerer datasæt ...")
    datasets = {}
    for bank, path in DATASETS:
        d = check_dataset(bank, path)
        if d:
            datasets[bank] = d
    check_comparison()
    check_comparable(datasets)

    print()
    print("Metrics pr. bank (alle produkter og horisonter):")
    for bank, d in datasets.items():
        o = d["overall"]
        if o["n"] == 0:
            continue
        print(f"  {bank:10s} n={o['n']:4d} bias={o['bias']:+.3f} "
              f"mae={o['mae']:.3f} opt={o['opt_share']:.0%}")

    print()
    for bank in ("nykredit", "sydbank"):
        d = datasets.get(bank)
        if not d:
            continue
        for p in d["order"]:
            m = d["metrics"][p].get("alle")
            if not m or m["n"] == 0:
                continue
            print(f"  {bank:9s} {d['labels'][p]:18s} n={m['n']:3d} "
                  f"bias={m['bias']:+.2f} mae={m['mae']:.2f} "
                  f"opt={m['opt_share']:.0%}")
        print()

    if failures:
        print(f"VALIDERING FEJLEDE: {len(failures)} problem(er)")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("VALIDERING OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
