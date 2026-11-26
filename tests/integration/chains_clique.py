# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SiliconBrane Inc.
"""Issue 30: the chains clique solver's contract on a board with no qualifying failure.

The hub's chains baseline leaves nothing open, so no chain runs and the clique must be
inert: identical tallies with the solver on and off, the options echo carrying the clique
fields with their defaults, and byte-stable JSON across two runs (chains is a measurement
command; its output is data). The live-fire evidence - sizif's single too_deep closing as
closed_clique with every other tally unchanged - is recorded on issue 30; no board in the
shipped fixtures exhibits a too_deep failure cheaply enough for CI.

Exit 77 (skipped) when the fixture is missing.
"""
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
FIX = ROOT / "bench/data/freerouting/scripts/benchmark/fixtures/PCBench"
SRC = FIX / "4-port-usb-hub_4port-usb-hub/unrouted.kicad_pcb"


def check(cond, msg):
    if not cond:
        raise SystemExit(f"FAIL: {msg}")


def chains(tm, work, tag, *extra):
    js = work / f"{tag}.json"
    p = subprocess.run([str(tm), "chains", str(SRC), "--json", str(js), *extra],
                       capture_output=True, text=True)
    check(p.returncode == 0, f"{tag}: chains rc {p.returncode}: {p.stdout[-300:]} {p.stderr[-200:]}")
    return json.loads(js.read_text())


def main():
    tm, work = sys.argv[1], pathlib.Path(sys.argv[2])
    if not SRC.exists():
        print(f"fixture missing: {SRC}")
        return 77
    work.mkdir(parents=True, exist_ok=True)

    on1 = chains(tm, work, "on1")
    on2 = chains(tm, work, "on2")
    check(on1 == on2, "two clique-on runs differ: chains output is not stable")
    opt = on1.get("options", {})
    for key, want in (("clique", True), ("clique_work", 8000000), ("clique_variants", 6), ("clique_max_nets", 12)):
        check(opt.get(key) == want, f"options echo: {key} is {opt.get(key)}, want {want}")
    check("closed_clique" not in on1.get("tally", {}), "clique fired on a board with no qualifying failure")

    off = chains(tm, work, "off", "--no-clique")
    check(off.get("options", {}).get("clique") is False, "--no-clique not echoed in options")
    check(off.get("tally") == on1.get("tally"), "tally changed with the clique off: the solver is not inert here")
    check(off.get("connections") == on1.get("connections"), "connection rows changed with the clique off")
    print("PASS chains_clique: options echo, inertness and stability on the hub fixture")
    return 0


if __name__ == "__main__":
    sys.exit(main())
