# -*- coding: utf-8 -*-
"""Valider dataset: overordnede metrics + spot-tjek af kendte perioder."""
import json

d = json.load(open("data/dataset.json", encoding="utf-8"))
print("meta:", json.dumps(d["meta"], ensure_ascii=False))
print("overall:", d["overall"])
print()
for p in d["order"]:
    m = d["metrics"][p]["alle"]
    print(f"{d['labels'][p]:18s} n={m['n']:3d} bias={m['bias']:+.2f}  "
          f"mae={m['mae']:.2f}  opt_andel={m['opt_share']:.0%}")
print()
print("F5-prognoser publiceret i 2022 (rentestødet) vs facit:")
for x in d["points"]:
    if x["p"] == "f5" and x["pub"] < "2023-01-01" and x["err"] is not None:
        print(f"  pub={x['pub']} target={x['target']} prognose={x['fc']:.2f} "
              f"facit={x['act']:.2f} fejl={x['err']:+.2f}")
print()
print("Fast30-prognoser publiceret i 2022 vs facit:")
for x in d["points"]:
    if x["p"] == "fast30" and x["pub"] < "2023-01-01" and x["err"] is not None:
        print(f"  pub={x['pub']} target={x['target']} prognose={x['fc']:.2f} "
              f"facit={x['act']:.2f} fejl={x['err']:+.2f}")
print()
print("Afventende (fremtidige mål uden facit endnu):",
      sum(1 for x in d["points"] if x["err"] is None))
print("Max facit-gap (dage):",
      max((x["gap_days"] or 0) for x in d["points"] if x["err"] is not None))
