#!/usr/bin/env python3
"""Read-only verification of Agent D's ND1/CE10 claims.

Extracts the 52 option-level line transitions from ladder_v7.txt MARKET_CHANGE
blocks, classifies each one three ways:
  - SPEC   : origin/phase1 parse_line_quarters (spec §5.2) -> same line? sign flip?
  - MAIN   : main events/line.py compare_line
  - CAND   : devcopy (BB-D1) events/line.py compare_line
and counts disagreements.

Also re-derives the ladder.txt per-series statistics (CE10).

READ ONLY: reads ladder.txt / ladder_v7.txt, and imports the pure events.line
modules with PYTHONDONTWRITEBYTECODE=1. No writes, no DB, no network.
"""
import ast
import os
import re
import subprocess
import sys

ROOT = "/data/data/com.androidharness.app/files/github-projects/bb-node-a6ff0096"
DEV = os.path.join(ROOT, "devcopy")
OUT = os.path.join(DEV, ".harness_tmp")

sys.path.insert(0, DEV)
from events import line as CAND  # noqa: E402


def load_main():
    """Load main's events/line.py under a distinct module name (pure module)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "main_line", os.path.join(ROOT, "events", "line.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


MAIN = load_main()


def load_plq():
    """Extract ONLY parse_line_quarters from origin/phase1:mapping/market.py
    and exec it in an isolated namespace (avoids importing that module's
    relative imports)."""
    src = subprocess.run(
        ["git", "-C", ROOT, "show", "origin/phase1:mapping/market.py"],
        capture_output=True, text=True, check=True).stdout
    tree = ast.parse(src)
    fn = next(n for n in tree.body
              if isinstance(n, ast.FunctionDef) and n.name == "parse_line_quarters")
    ns = {}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), "<plq>", "exec"), ns)
    return ns["parse_line_quarters"]


PLQ = load_plq()


# ---------- ladder_v7.txt : reconstruct option-level transitions ----------
def transitions(path):
    """Yield (ts, match_id, option, old_line, new_line) from MARKET_CHANGE blocks."""
    out = []
    ts = mid = None
    minus = {}   # option -> line   (market that disappeared)
    plus = {}    # option -> line   (market that appeared)
    tuple_re = re.compile(r"\('([^']+)',\s*'([^']*)'")
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.rstrip("\n")
            if "MARKET_CHANGE" in line:
                parts = line.split()
                ts, mid = parts[0], parts[1]
                minus, plus = {}, {}
                continue
            m = re.match(r"^\s*([-+])\s+(\d+)\s+\[(.*)\]\s*$", line)
            if not m:
                continue
            sign, _mid, body = m.groups()
            target = plus if sign == "+" else minus
            for name, ln in tuple_re.findall(body):
                target[name] = ln
                continue
    return out


def transitions_v7(path):
    """Correct two-pass: a block is complete when a NEW block header or EOF hits."""
    out = []
    blocks = []
    cur = None
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.rstrip("\n")
            if "MARKET_CHANGE" in line:
                parts = line.split()
                if cur:
                    blocks.append(cur)
                cur = {"ts": parts[0], "mid": parts[1], "minus": {}, "plus": {}}
                continue
            m = re.match(r"^\s*([-+])\s+(\d+)\s+\[(.*)\]\s*$", line)
            if not m or cur is None:
                continue
            sign, _id, body = m.groups()
            target = cur["plus"] if sign == "+" else cur["minus"]
            for name, ln in re.findall(r"\('([^']+)',\s*'([^']*)'", body):
                target[name] = ln
    if cur:
        blocks.append(cur)
    for b in blocks:
        for opt, old in b["minus"].items():
            if opt in b["plus"]:
                out.append((b["ts"], b["mid"], opt, old, b["plus"][opt]))
    return out


def ladder_txt_stats(path):
    """(match,market,option) series and how many have >1 distinct line string."""
    series = {}
    rows = 0
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            parts = raw.rstrip("\n").split(" | ")
            if len(parts) != 3:
                continue
            mid = parts[0].split()[1]
            mk = parts[1].strip()
            for item in parts[2].split(","):
                opt, ln, _od = item.split(":")
                rows += 1
                series.setdefault((mid, mk, opt), set()).add(ln)
    multi = {k: v for k, v in series.items() if len(v) > 1}
    return rows, len(series), multi


def main():
    print("=" * 78)
    print("A. ladder.txt per-series statistics (verify CE10)")
    print("=" * 78)
    rows, nser, multi = ladder_txt_stats(os.path.join(ROOT, "ladder.txt"))
    print(f"  option rows parsed      : {rows}")
    print(f"  (match,market,option)   : {nser}")
    print(f"  series with >1 distinct line string : {len(multi)}")
    for k, v in list(multi.items())[:10]:
        print(f"     {k} -> {sorted(v)}")
    print("  => ladder.txt contains "
          f"{'NO' if not multi else 'SOME'} line changes at all")

    print()
    print("=" * 78)
    print("B. ladder_v7.txt option-level transitions vs SPEC / MAIN / CANDIDATE")
    print("=" * 78)
    trs = transitions_v7(os.path.join(ROOT, "ladder_v7.txt"))
    print(f"  option-level transitions recovered : {len(trs)}")
    n_spec_flip = n_spec_same = 0
    main_seen = cand_seen = 0
    spec_flip_missed_main, spec_flip_missed_cand = [], []
    false_pos_main, false_pos_cand = [], []
    flip_seen_main, flip_seen_cand = [], []
    for ts, mid, opt, old, new in trs:
        qo, mo = PLQ(old)
        qn, mn = PLQ(new)
        spec_same = (qo == qn)
        spec_flip = (not spec_same) and (mo != 0) and (mn != 0) and \
                    ((mo > 0) != (mn > 0))
        if spec_same:
            n_spec_same += 1
        elif spec_flip:
            n_spec_flip += 1
        rm = MAIN.compare_line(old, new)
        rc = CAND.compare_line(old, new)
        if rm["changed"]:
            main_seen += 1
        if rc["changed"]:
            cand_seen += 1
        if spec_flip:
            if not rm["changed"]:
                spec_flip_missed_main.append((ts, mid, opt, old, new))
            if not rc["changed"]:
                spec_flip_missed_cand.append((ts, mid, opt, old, new))
            if rm["changed"]:
                flip_seen_main.append((ts, mid, opt, old, new, rm))
            if rc["changed"]:
                flip_seen_cand.append((ts, mid, opt, old, new, rc))
        else:
            if rm["changed"]:
                false_pos_main.append((ts, mid, opt, old, new, rm))
            if rc["changed"]:
                false_pos_cand.append((ts, mid, opt, old, new, rc))
    print(f"  SPEC: same-line transitions = {n_spec_same} | sign-flip transitions = {n_spec_flip}")
    print(f"  MAIN  changed=True count = {main_seen}")
    print(f"  CAND  changed=True count = {cand_seen}")
    print()
    print(f"  spec sign-flips MISSED by main   : {len(spec_flip_missed_main)}")
    for t in spec_flip_missed_main:
        print(f"     {t[0]} match={t[1]} {t[2]}: {t[3]!r} -> {t[4]!r}")
    print(f"  spec sign-flips MISSED by candidate: {len(spec_flip_missed_cand)}")
    for t in spec_flip_missed_cand:
        print(f"     {t[0]} match={t[1]} {t[2]}: {t[3]!r} -> {t[4]!r}")
    print(f"  FALSE POSITIVES main (spec says same/not-flip, main says changed) : {len(false_pos_main)}")
    for t in false_pos_main:
        print(f"     {t[0]} match={t[1]} {t[2]}: {t[3]!r} -> {t[4]!r}  {t[5]}")
    print(f"  FALSE POSITIVES candidate : {len(false_pos_cand)}")
    for t in false_pos_cand:
        print(f"     {t[0]} match={t[1]} {t[2]}: {t[3]!r} -> {t[4]!r}  {t[5]}")

    print()
    print("=" * 78)
    print("C. how each implementation labels a detected spec-flip (units differ?)")
    print("=" * 78)
    for ts, mid, opt, old, new, rm in flip_seen_main[:8]:
        rc = CAND.compare_line(old, new)
        print(f"  {old!r:>12} -> {new!r:<12} MAIN {rm['direction']}/{rm['change_type']}/{rm['steps']}"
              f"   CAND {rc['direction']}/{rc['change_type']}/{rc['steps']}")

    print()
    print("=" * 78)
    print("D. plq robustness spot-checks (verify CE2/CE3/CE4)")
    print("=" * 78)
    for s in ["0.125", "0.625", "-0.5/-0.25", "-1/+1", "inf", "1e400", "0.1", "-0", "0"]:
        try:
            print(f"  plq({s!r}) = {PLQ(s)}")
        except Exception as e:
            print(f"  plq({s!r}) RAISED {type(e).__name__}: {e}")


main()
