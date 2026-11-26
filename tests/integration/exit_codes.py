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
"""Trustworthy exit codes + structured failures (Tier 1 ask #4).

  exit_codes.py <tracemaker> <work dir>

The documented matrix for `route`: 0 = every connection routed; 3 = the job ran but
connections remain open; 1 = the job failed to run; 2 = usage error (CLI11's own parse
codes -- 105, 106, ... -- are normalized, they are not the contract).

  complete: usb-hub with its one hard net skipped -> rc 0, summary exit_code 0,
            open_connections empty. (No --soft-zones here: with them the exit code
            prices the refilled board, where a deliberately skipped net's pads
            still count as unconnected -- rc 3 there is the honest answer.)
  partial:  usb-hub with the plugin flag mix -> rc 3, summary exit_code 3, and every
            open_connections entry is an object {net, reason, from{part, pad},
            to{part, pad} | {zone}} with a reason from the router's stable vocabulary;
            the human-readable failures strings are still there beside it.
  failed:   a corrupt board file -> rc 1.
  usage:    an unknown flag and a missing -o -> rc 2; --help stays rc 0.
Exit 77 (skipped) when the fixture is missing.
"""
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
FIX = ROOT / "bench/data/freerouting/scripts/benchmark/fixtures/PCBench"
SRC = FIX / "4-port-usb-hub_4port-usb-hub/unrouted.kicad_pcb"
REASONS = {"boxed_in", "exact_check", "rip_limit", "ripped_not_rerouted", "layer_limit",
           "out_of_budget", "rolled_back", "not_attempted", "no_legal_path"}
MIX = ["--seed", "42", "--soft-zones", "--keep-vias-off-pads", "--diff-pairs", "--si-rules", "--critical-auto", "--no-gpu"]


def check(cond, msg):
    if not cond:
        raise SystemExit(f"FAIL: {msg}")


def run(tm, *args):
    return subprocess.run([str(tm), *args], capture_output=True, text=True)


def main():
    tm, work = sys.argv[1], pathlib.Path(sys.argv[2])
    if not SRC.exists():
        print(f"fixture missing: {SRC}")
        return 77
    work.mkdir(parents=True, exist_ok=True)

    js = work / "complete.json"
    p = run(tm, "route", str(SRC), "-o", str(work / "complete.kicad_pcb"), "--json", str(js),
            "--work", "1000000", "--skip-net", "D2-", *[f for f in MIX if f != "--soft-zones"])
    check(p.returncode == 0, f"complete: rc {p.returncode} != 0: {p.stderr[-500:]}")
    s = json.loads(js.read_text())
    check(s.get("exit_code") == 0, f"complete: summary exit_code {s.get('exit_code')} != 0")
    check(s.get("exit_reason") == "complete", f"complete: summary exit_reason {s.get('exit_reason')} != complete")
    check(s.get("open_connections") == [], f"complete: open_connections not empty: {s.get('open_connections')}")
    print(f"complete: rc 0, {s['routed']}/{s['connections']} routed")

    js = work / "partial.json"
    p = run(tm, "route", str(SRC), "-o", str(work / "partial.kicad_pcb"), "--json", str(js),
            "--work", "1000000", *MIX)
    check(p.returncode == 3, f"partial: rc {p.returncode} != 3: {p.stderr[-500:]}")
    s = json.loads(js.read_text())
    check(s.get("exit_code") == 3, f"partial: summary exit_code {s.get('exit_code')} != 3")
    want_reason = "unconnected_after_refill" if (s.get("unconnected_after_refill") or 0) > 0 else "open_connections"
    check(s.get("exit_reason") == want_reason, f"partial: summary exit_reason {s.get('exit_reason')} != {want_reason}")
    oc = s.get("open_connections")
    check(isinstance(oc, list) and len(oc) == s["connections"] - s["routed"] and len(oc) > 0,
          f"partial: open_connections does not match the open count: {oc}")
    for e in oc:
        check(isinstance(e.get("net"), str) and e["net"], f"partial: entry without a net: {e}")
        check(e.get("reason") in REASONS, f"partial: reason not in the stable vocabulary: {e}")
        for end in ("from", "to"):
            v = e.get(end)
            check(isinstance(v, dict) and (("part" in v and "pad" in v) or v.get("zone") is True),
                  f"partial: {end} is not a REF.PIN pair or a zone: {e}")
    check(isinstance(s.get("failures"), list), "partial: the failures strings are gone")
    print(f"partial: rc 3, open_connections {[(e['net'], e['reason']) for e in oc]}")

    bad = work / "corrupt.kicad_pcb"
    bad.write_text("this is not a board")
    p = run(tm, "route", str(bad), "-o", str(work / "x.kicad_pcb"))
    check(p.returncode == 1, f"failed: rc {p.returncode} != 1")
    print("failed: rc 1")

    p = run(tm, "route", str(SRC), "-o", str(work / "x.kicad_pcb"), "--bogus-flag")
    check(p.returncode == 2, f"usage (unknown flag): rc {p.returncode} != 2")
    p = run(tm, "route", str(SRC))
    check(p.returncode == 2, f"usage (missing -o): rc {p.returncode} != 2")
    p = run(tm, "route", "--help")
    check(p.returncode == 0, f"usage (--help): rc {p.returncode} != 0")
    print("usage: rc 2 / 2, --help rc 0")

    print("exit_codes: all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
