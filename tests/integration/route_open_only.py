#!/usr/bin/env python3
# Copyright (C) 2026 SiliconBrane Inc.
#
# This file is part of TraceMaker (SiliconBrane fork).
#
# TraceMaker is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# TraceMaker is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with TraceMaker. If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# SPDX-License-Identifier: GPL-3.0-or-later
"""--route-open-only finisher mode (Tier 1 ask #3).

  route_open_only.py <tracemaker> <work dir>

  finisher: a usb-hub board routed cheaply (3 connections left open) is finished with
            --route-open-only --work 20000000: the summary reports route_open_only and
            open_at_start (the input's ratsnest), and the focused repair windows close
            the rest -- the run must end with at most 1 open, strictly fewer than it
            started with, the exit code agreeing (0 when none remain, else 3).
  refusal:  --route-open-only with --repair off is refused (rc 1).
  degenerate: on a board with no routed copper the mode is a plain route whose repair
            stage still runs in finisher form (it may even complete a small board):
            route_open_only reported, open_at_start is the whole ratsnest, and the
            exit code agrees with the summary's own exit_code.
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


def route(tm, board, out, js, *extra):
    p = subprocess.run([str(tm), "route", str(board), "-o", str(out), "--json", str(js), "--no-gpu", *extra],
                       capture_output=True, text=True)
    return p


def main():
    tm, work = sys.argv[1], pathlib.Path(sys.argv[2])
    if not SRC.exists():
        print(f"fixture missing: {SRC}")
        return 77
    work.mkdir(parents=True, exist_ok=True)

    pj = work / "partial.json"
    p = route(tm, SRC, work / "partial.kicad_pcb", pj, "--work", "300000", "--seed", "42")
    check(p.returncode == 3, f"partial: rc {p.returncode} != 3")
    ps = json.loads(pj.read_text())
    open_start = ps["connections"] - ps["routed"]
    check(open_start >= 2, f"partial: only {open_start} open, the finisher has nothing to prove")
    print(f"partial: {ps['routed']}/{ps['connections']} routed, {open_start} open")

    fj = work / "finished.json"
    p = route(tm, work / "partial.kicad_pcb", work / "finished.kicad_pcb", fj,
              "--route-open-only", "--work", "20000000", "--seed", "42")
    check(p.returncode in (0, 3), f"finisher: rc {p.returncode}: {p.stderr[-500:]}")
    fs = json.loads(fj.read_text())
    check(fs.get("route_open_only") is True, "finisher: route_open_only missing from the summary")
    check(fs.get("open_at_start") == open_start,
          f"finisher: open_at_start {fs.get('open_at_start')} != the input's {open_start}")
    open_final = fs["connections"] - fs["routed"]
    check(open_final < open_start, f"finisher: open {open_final} did not improve on {open_start}")
    check(open_final <= 1, f"finisher: {open_final} still open after a 20M per-connection budget")
    check(p.returncode == (0 if open_final == 0 else 3),
          f"finisher: rc {p.returncode} disagrees with {open_final} open")
    print(f"finisher: open {open_start} -> {open_final}, rc {p.returncode}")

    p = route(tm, SRC, work / "x.kicad_pcb", work / "x.json", "--route-open-only", "--repair", "off")
    check(p.returncode == 1, f"refusal: rc {p.returncode} != 1: {p.stderr[-300:]}")
    check("--route-open-only" in p.stderr, f"refusal: the error does not name the mode: {p.stderr[-300:]}")
    print("refusal: --repair off refused")

    dj = work / "degenerate.json"
    p = route(tm, SRC, work / "degenerate.kicad_pcb", dj, "--route-open-only", "--work", "1000000", "--seed", "42")
    check(p.returncode in (0, 3), f"degenerate: rc {p.returncode}")
    ds = json.loads(dj.read_text())
    check(p.returncode == ds.get("exit_code"), f"degenerate: rc {p.returncode} != summary exit_code {ds.get('exit_code')}")
    check(ds.get("route_open_only") is True, "degenerate: route_open_only missing")
    check(ds.get("open_at_start") == ds["connections"],
          f"degenerate: open_at_start {ds.get('open_at_start')} != connections {ds['connections']}")
    print(f"degenerate: plain route, open_at_start {ds['open_at_start']}")

    print("route_open_only: all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
