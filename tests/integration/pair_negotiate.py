#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Issue 38 item 3b: --pair-negotiate lets a pair displace routed connections, atomically.

  pair_negotiate.py <tracemaker> <work dir>

Routes the PCBench 4-port USB hub with --diff-pairs --finish, twice. In the plain run all five pairs
now couple (the weakest, D3, at 0.845). With --pair-negotiate the finish ladder's first rung couples
two of the pairs by negotiation - the log says so - the weakest pair improves (D3 0.897), every pair
ends at 0.85 or better, and no connection is lost: negotiation is atomic, it never trades a pair for
a stranded single.

History: as first written, this test asserted the plain run leaves D3 split (share 0.0) and the
negotiated run couples it (0.903). Issue 37's landing changed the hub's plain run - D3 couples
without negotiation - so that premise is gone; what survives, and what this test now asserts, is that
negotiation still fires on this board (at the ladder's first rung), that it does not harm any pair,
and that it improves the weakest one. The original D3 evidence is recorded on issue 38.
"""
import json
import os
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
FIX = pathlib.Path(os.environ.get("TM_FIXTURES", ROOT / "bench/data/freerouting/scripts/benchmark/fixtures/PCBench"))
SRC = FIX / "4-port-usb-hub_4port-usb-hub/unrouted.kicad_pcb"

errors = []


def check(cond, text):
    if not cond:
        errors.append(text)


def route(tm, work, name, extra):
    out = work / f"{name}.kicad_pcb"
    js = work / f"{name}.json"
    r = subprocess.run([str(tm), "route", str(SRC), "-o", str(out), "--json", str(js), "--diff-pairs", "--finish",
                        "--deterministic", "--work", "20000000", "--variants", "1", "--threads", "1",
                        "--no-kb", "--no-gpu"] + extra, capture_output=True, text=True)
    if r.returncode not in (0, 3):
        sys.exit(f"{name}: tracemaker failed\n{r.stdout[-1500:]}\n{r.stderr[-1500:]}")
    pj = work / f"{name}_pairs.json"
    subprocess.run([str(tm), "pairs", str(out), "--json", str(pj)], check=True, capture_output=True)
    pairs = {(p["net_a"], p["net_b"]): p for p in json.loads(pj.read_text())["pairs"]}
    return r.stdout, json.loads(js.read_text()), pairs


def main() -> int:
    tm, work = sys.argv[1], pathlib.Path(sys.argv[2])
    if not SRC.exists():
        print(f"skip: hub fixture not present at {SRC}")
        return 77
    work.mkdir(parents=True, exist_ok=True)
    _, plain, pp = route(tm, work, "plain", [])
    check(plain["routed"] == plain["connections"], f"plain run completes (routed {plain['routed']}/{plain['connections']})")
    check(len(pp) == 5, f"plain run: five pairs measured, got {len(pp)}")
    pmin = min((p["coupled_share"] for p in pp.values()), default=0.0)
    check(pmin >= 0.80, f"plain run: every pair couples since issue 37 (weakest share {pmin:.3f})")
    print(f"plain: weakest share {pmin:.3f}, routed {plain['routed']}/{plain['connections']}")
    stdout, neg, npairs = route(tm, work, "neg", ["--pair-negotiate"])
    check("coupled by negotiation" in stdout, "negotiated run must log pairs coupled by negotiation")
    check(neg["routed"] == neg["connections"], f"negotiated run completes (routed {neg['routed']}/{neg['connections']})")
    check(len(npairs) == 5, f"negotiated run: five pairs measured, got {len(npairs)}")
    nmin = min((p["coupled_share"] for p in npairs.values()), default=0.0)
    check(nmin >= 0.85, f"negotiated run: every pair at 0.85 or better (weakest {nmin:.3f})")
    check(nmin >= pmin, f"negotiation does not harm the weakest pair ({nmin:.3f} >= {pmin:.3f})")
    for p in npairs.values():
        check(p["gap_min_mm"] >= p["target_gap_mm"] - 1e-3,
              f"negotiated pair {p['net_a']}: gap {p['gap_min_mm']:.3f} below target {p['target_gap_mm']:.3f}")
    print(f"negotiated: weakest share {nmin:.3f}, routed {neg['routed']}/{neg['connections']}")
    if not errors and shutil.which("kicad-cli"):
        drc = subprocess.run(["kicad-cli", "pcb", "drc", "--format", "json", "--severity-error",
                              "--output", str(work / "neg_drc.json"), str(work / "neg.kicad_pcb")],
                             capture_output=True, text=True)
        if drc.returncode == 0:
            rep = json.loads((work / "neg_drc.json").read_text())
            bad = [v for v in rep.get("violations", []) if v["type"] in ("clearance", "shorting_items", "tracks_crossing")]
            check(not bad, f"KiCad DRC on the negotiated output: {bad[:3]}")
            check(not rep.get("unconnected_items"), "KiCad DRC: negotiated output has unconnected items")
    for e in errors:
        print("FAIL:", e)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
