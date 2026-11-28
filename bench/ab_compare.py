#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Phase 4A A/B comparison: two bench runs of the same boards, board by board.

  bench/ab_compare.py RUN_A RUN_B

Reports per-board vias (base -> opt), completion, clean, and drc_judge added
errors, plus totals. Added errors in the opt arm are the hard gate: must be 0
wherever the base arm has 0.
"""
import json, pathlib, sys

def load(d):
    out = {}
    for line in (pathlib.Path(d) / "boards.jsonl").read_text().splitlines():
        r = json.loads(line)
        out[r["board"]] = r
    return out

def added(r):
    return sum(r.get("added_errors", {}).values())

def main():
    a, b = load(sys.argv[1]), load(sys.argv[2])
    tv_a = tv_b = 0
    print(f"{'board':46} {'vias A->B':>12} {'compl A->B':>15} {'clean':>7} {'addedA/B':>9}")
    for name in a:
        ra, rb = a[name], b.get(name)
        if rb is None:
            print(f"{name[:46]:46} missing in B")
            continue
        va, vb = ra["style"]["vias"], rb["style"]["vias"]
        tv_a += va; tv_b += vb
        print(f"{name[:46]:46} {va:5} -> {vb:<5} {ra['completion']:.3f} -> {rb['completion']:.3f}  {str(ra['clean'])[:1]}/{str(rb['clean'])[:1]}   {added(ra)}/{added(rb)}")
    print(f"{'TOTAL':46} {tv_a:5} -> {tv_b:<5} delta {tv_b - tv_a:+d} vias")
    return 0

if __name__ == "__main__":
    sys.exit(main())
