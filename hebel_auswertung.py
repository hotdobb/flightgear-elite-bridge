"""Fasst ein dekodiertes Log zusammen: welcher Code wurde wann bewegt, mit welchem Bereich."""

import re
import sys

datei = sys.argv[1] if len(sys.argv) > 1 else "hebel_alle.log"
muster = re.compile(r"\s*([\d.]+)s\s+Code\s+(\d+)\s+(.+?)\s+=\s+(\d+)\s+\(vorher")
codes = {}
for zeile in open(datei, encoding="utf-8"):
    m = muster.match(zeile)
    if not m:
        continue
    zeit, code, name, wert = float(m[1]), int(m[2]), m[3], int(m[4])
    c = codes.setdefault(code, {"name": name, "von": zeit, "bis": zeit, "min": wert,
                                "max": wert, "n": 0})
    c["bis"] = zeit
    c["min"] = min(c["min"], wert)
    c["max"] = max(c["max"], wert)
    c["n"] += 1

for code, c in sorted(codes.items(), key=lambda kv: kv[1]["von"]):
    print(f"{c['von']:6.1f}-{c['bis']:5.1f}s  Code {code:3d} {c['name']:<14} "
          f"{c['min']:3d}..{c['max']:3d}  ({c['n']} Aenderungen)")
