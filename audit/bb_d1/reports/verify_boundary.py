#!/usr/bin/env python3
"""Full boundary-value matrix: main parse_line | candidate value | spec parse_line_quarters.

READ ONLY. Prints one row per input.
"""
import ast
import importlib.util
import os
import subprocess
import sys

ROOT = "/data/data/com.androidharness.app/files/github-projects/bb-node-a6ff0096"
DEV = os.path.join(ROOT, "devcopy")

spec = importlib.util.spec_from_file_location(
    "main_line", os.path.join(ROOT, "events", "line.py"))
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)

sys.path.insert(0, DEV)
from events import line as C  # candidate

src = subprocess.run(["git", "-C", ROOT, "show", "origin/phase1:mapping/market.py"],
                     capture_output=True, text=True, check=True).stdout
tree = ast.parse(src)
fn = next(n for n in tree.body
          if isinstance(n, ast.FunctionDef) and n.name == "parse_line_quarters")
ns = {}
exec(compile(ast.Module(body=[fn], type_ignores=[]), "<plq>", "exec"), ns)
PLQ = ns["parse_line_quarters"]

INPUTS = [
    "-0/0.5", "+0/0.5", "0/0.5", "-0.5/0", "+0.5/0",
    "-0.5", "+0.5", "-0.5/1", "+0.5/1",
    " -0/0.5 ", "-0/0.5 ", "-0 / 0.5", "--0.5", "+-0.5",
    "", None, "abc", "1/2/3", "0", "-0", "+0", "2", "2.5", "0.125", "0.625",
    "-1/+1", "inf", "1e400", "0.1",
]

hdr = (f"{'input':<12} | {'main legs':<20} | {'main depth':<10} | {'cand value':<10} | "
       f"{'spec quarters':<14} | {'spec mid':<8} | cand==spec?")
print(hdr)
print("-" * len(hdr))
for s in INPUTS:
    try:
        mn = M.norm(s)
    except Exception as e:
        mn = f"EXC {type(e).__name__}"
    try:
        cn = C.norm(s)
    except Exception as e:
        cn = f"EXC {type(e).__name__}"
    try:
        q, mid = PLQ(s)
    except Exception as e:
        q, mid = f"EXC {type(e).__name__}", "-"

    legs = mn["legs"] if isinstance(mn, dict) else str(mn)
    depth = mn["depth"] if isinstance(mn, dict) else "-"
    val = cn["value"] if isinstance(cn, dict) else "-"
    # candidate value expressed in quarter balls vs spec mid
    agree = "-"
    if isinstance(cn, dict) and not str(q).startswith("EXC"):
        cand_q = round(val * 4) if val is not None else None
        agree = "YES" if cand_q == mid else "NO"
    print(f"{repr(s):<12} | {str(legs):<20} | {str(depth):<10} | {str(val):<10} | "
          f"{str(q):<14} | {str(mid):<8} | {agree}")
