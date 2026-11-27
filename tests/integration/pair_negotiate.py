#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Issue 38 item 3: --pair-negotiate couples a pair the strict search leaves split, atomically.

  pair_negotiate.py <tracemaker> <workdir>

Routes PCBench 4-port-usb-hub with --diff-pairs --finish at a fixed work budget, twice. In the
plain run the D3 pair ends split (coupled share ~0): its coupled corridor is occupied by routed
singles by the time the clean-up tries to couple it, and the strict coupled search may not touch
them. With --pair-negotiate the pair displaces those singles and is kept only because every
displaced connection routes again - the board still completes (the transaction property), D3
couples over at least 85 % of its length at its gap, and the number of coupled pairs does not
drop. (On this fixture the coupled set changes membership: D0, coupled in the plain run, is the
pair left split in the negotiated run - the coupled corridors of D0 and D3 contend, and
negotiation changes who wins. The flag is opt-in for boards where the split pair matters more.)
Exit 77 when the fixture is missing (TM_FIXTURES overrides the PCBench directory).
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


def route(tm, work, name, extra):
    out = work / f"{name}.kicad_pcb"
    js = work / f"{name}.json"
    r = subprocess.run([tm, "route", str(SRC), "-o", str(out), "--json", str(js), "--diff-pairs", "--finish",
                        "--deterministic", "--work", "20000000", "--variants", "1", "--threads", "1",
                        "--no-kb", "--no-gpu"] + extra, capture_output=True, text=True)
    pj = work / f"{name}_pairs.json"
    subprocess.run([tm, "pairs", str(out), "--json", str(pj)], check=True, capture_output=True)
    pairs = {(p["net_a"], p["net_b"]): p for p in json.loads(pj.read_text())["pairs"]}
    return r.stdout, json.loads(js.read_text()), pairs


def check(cond, msg):
    if not cond:
        print("FAIL:", msg)
        sys.exit(1)
    print("ok:", msg)


def main() -> int:
    tm, work = sys.argv[1], pathlib.Path(sys.argv[2])
    if not SRC.exists():
        print("fixture missing: skipped")
        return 77
    work.mkdir(parents=True, exist_ok=True)
    _, plain, pp = route(tm, work, "neg_plain", [])
    out, neg, pn = route(tm, work, "neg_neg", ["--pair-negotiate"])
    check(plain["open"] == 0 and neg["open"] == 0, f"both runs complete (plain open {plain['open']}, negotiated open {neg['open']})")
    check(len(pp) == 5 and len(pn) == 5, "five pairs measured in both runs")
    d3p, d3n = pp[("D3+", "D3-")], pn[("D3+", "D3-")]
    check(d3p["coupled_share"] < 0.05, f"plain run leaves D3 split (share {d3p['coupled_share']:.3f})")
    check("coupled by negotiation" in out, "the negotiated run reports a pair coupled by negotiation")
    check(d3n["coupled_share"] >= 0.85, f"negotiation couples D3 (share {d3n['coupled_share']:.3f})")
    check(d3n["gap_min_mm"] >= d3n["target_gap_mm"] - 1e-3, f"D3 keeps its gap (min {d3n['gap_min_mm']:.3f} of {d3n['target_gap_mm']:.3f})")
    coupled = lambda ps: sum(1 for p in ps.values() if p["coupled_share"] >= 0.85)
    check(coupled(pn) >= coupled(pp), f"coupled pairs do not drop ({coupled(pp)} plain, {coupled(pn)} negotiated)")
    if shutil.which("kicad-cli"):
        for name in ("neg_plain", "neg_neg"):
            drc = work / f"{name}_drc.json"
            subprocess.run(["kicad-cli", "pcb", "drc", "--format", "json", "--severity-all", "-o", str(drc), str(work / f"{name}.kicad_pcb")], capture_output=True)
            v = json.loads(drc.read_text())
            bad = [x for x in v["violations"] if x["severity"] == "error" and any(i["description"].startswith(("Track", "Via")) for i in x["items"])]
            check(not bad and not v["unconnected_items"], f"{name}: KiCad DRC clean (unconnected {len(v['unconnected_items'])}, copper errors {len(bad)})")
    print("pair_negotiate: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
