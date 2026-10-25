#!/usr/bin/env python3
"""Precise 3-way confusion matrix over the 52 real option-level line transitions.

SPEC   = origin/phase1 parse_line_quarters  -> SAME | FLIP | MAGNITUDE
MAIN   = main events/line.py compare_line    -> SAME | MAGNITUDE (no flip concept)
CAND   = devcopy BB-D1 compare_line         -> SAME | MAGNITUDE | CROSS

READ ONLY. Reuses the transition extractor from verify_claims.py.
"""
import importlib.util
import os
import sys

OUT = "/data/data/com.androidharness.app/files/github-projects/bb-node-a6ff0096/devcopy/.harness_tmp"
sys.path.insert(0, OUT)
spec = importlib.util.spec_from_file_location("vc", os.path.join(OUT, "verify_claims.py"))
# import helpers without running main()
src = open(os.path.join(OUT, "verify_claims.py")).read()
# drop only the trailing driver call, keep every helper
cut = src.rindex("\nmain()")
src = src[:cut]
ns = {}
exec(compile(src, "vc", "exec"), ns)

ROOT = ns["ROOT"]
PLQ = ns["PLQ"]
MAIN = ns["MAIN"]
CAND = ns["CAND"]
transitions_v7 = ns["transitions_v7"]


def spec_class(old, new):
    qo, mo = PLQ(old)
    qn, mn = PLQ(new)
    if qo == qn:
        return "SAME", mo, mn
    if mo != 0 and mn != 0 and ((mo > 0) != (mn > 0)):
        return "FLIP", mo, mn
    return "MAGNITUDE", mo, mn


def impl_class(r):
    if r["changed"] is None:
        return "UNKNOWN"
    if not r["changed"]:
        return "SAME"
    if r["direction"] == "CROSS":
        return "FLIP"
    return "MAGNITUDE"


trs = transitions_v7(os.path.join(ROOT, "ladder_v7.txt"))
print(f"real option-level transitions: {len(trs)}\n")

matrix = {}
rows = []
for ts, mid, opt, old, new in trs:
    sc, mo, mn = spec_class(old, new)
    mc = impl_class(MAIN.compare_line(old, new))
    cc = impl_class(CAND.compare_line(old, new))
    matrix[(sc, mc, cc)] = matrix.get((sc, mc, cc), 0) + 1
    rows.append((ts, mid, opt, old, new, sc, mo, mn, mc, cc))

print("=== CONFUSION MATRIX  (SPEC -> MAIN / SPEC -> CANDIDATE) ===")
for sc in ("SAME", "MAGNITUDE", "FLIP"):
    for impl_name, idx in (("MAIN", 1), ("CAND", 2)):
        dist = {}
        for (s, m, c), n in matrix.items():
            if s == sc:
                dist[(m, c)[idx - 1]] = dist.get((m, c)[idx - 1], 0) + n
        print(f"  SPEC={sc:<9} {impl_name:<4} -> {dist}")

print("\n=== CANDIDATE misclassifications (spec != candidate) ===")
bad = [r for r in rows if r[5] != r[9]]
print(f"  total mismatches: {len(bad)}")
for ts, mid, opt, old, new, sc, mo, mn, mc, cc in bad:
    print(f"   {ts} match={mid} {opt}: {old!r} -> {new!r}")
    print(f"        SPEC={sc} (mid {mo}->{mn}, in quarter balls)  MAIN={mc}  CAND={cc}")

print("\n=== the 2 sides of the same market move, classified by each impl ===")
seen = {}
for ts, mid, opt, old, new, sc, mo, mn, mc, cc in rows:
    seen.setdefault((ts, mid, old, new), []).append((opt, sc, mc, cc))
for (ts, mid, old, new), lst in seen.items():
    if len(lst) == 2 and lst[0][2] != lst[1][2]:
        print(f"   {ts} match={mid} {old!r} -> {new!r}")
        for opt, sc, mc, cc in lst:
            print(f"        {opt:<10} SPEC={sc:<9} MAIN={mc:<9} CAND={cc}")
