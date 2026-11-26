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
"""--finish-rip-walls (DR-22 Tier 2-prime, issue #27).

  finish_rip_walls.py <tracemaker> <work dir>

  baseline:  usb-hub finished with --finish --deterministic --work 20000000.
  rip:       the same recipe plus --finish-rip-walls, run twice. The two rip runs must be
             byte-identical (the phase is deterministic: proof, rip set and heal all are),
             and the rip result must not be worse than the baseline under the keep price
             (open + walled, both priced by a --work 1 proof over each output board).
             Any rip round rows in the finish list must obey the keep rule themselves:
             a kept round improves open + walled (or ties it with fewer open), a discarded
             round does not, and the final open count is the last kept round open_after.
Exit 77 (skipped) when the fixture is missing.
"""
import hashlib
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
    return subprocess.run([str(tm), "route", str(board), "-o", str(out), "--json", str(js), "--no-gpu", *extra],
                          capture_output=True, text=True)


def price(tm, work, board, tag):
    js = work / f"{tag}-proof.json"
    p = route(tm, board, work / f"{tag}-proof.kicad_pcb", js, "--work", "1")
    check(p.returncode in (0, 3), f"{tag}: proof rc {p.returncode}")
    s = json.loads(js.read_text())
    wo = s.get("why_open", {})
    return s["connections"] - s["routed"], wo.get("walled_in", 0)


def finish(tm, work, tag, *extra):
    js = work / f"{tag}.json"
    out = work / f"{tag}.kicad_pcb"
    p = route(tm, SRC, out, js, "--finish", "--deterministic", "--work", "20000000", *extra)
    check(p.returncode in (0, 3), f"{tag}: finish rc {p.returncode}: {p.stdout[-400:]} {p.stderr[-200:]}")
    s = json.loads(js.read_text())
    check(s.get("deterministic") is True, f"{tag}: summary does not claim deterministic")
    return out, s


def main():
    tm, work = sys.argv[1], pathlib.Path(sys.argv[2])
    if not SRC.exists():
        print(f"fixture missing: {SRC}")
        return 77
    work.mkdir(parents=True, exist_ok=True)

    base_out, base = finish(tm, work, "base")
    base_open, base_walled = price(tm, work, base_out, "base")
    check(base["finish"]["open"] == base_open, f"base: finish open disagrees with proof open {base_open}")

    outs = []
    for tag in ("rip1", "rip2"):
        out, s = finish(tm, work, tag, "--finish-rip-walls")
        outs.append((out, s))
    h = [hashlib.sha256(o.read_bytes()).hexdigest() for o, _ in outs]
    check(h[0] == h[1], "rip runs differ: the phase is not deterministic")
    rows_a = [r for r in outs[0][1]["finish"]["rungs"] if str(r.get("rung", "")).startswith("rip walls")]
    rows_b = [r for r in outs[1][1]["finish"]["rungs"] if str(r.get("rung", "")).startswith("rip walls")]
    check(rows_a == rows_b, "rip rows differ between the two runs")

    rip_open, rip_walled = price(tm, work, outs[0][0], "rip")
    check(rip_open + rip_walled <= base_open + base_walled,
          f"rip price {rip_open}+{rip_walled} worse than baseline {base_open}+{base_walled}")
    check(outs[0][1]["finish"]["open"] == rip_open, "rip: finish open != proof open")

    expect_open = base_open
    for r in rows_a:
        price_before = r["open_before"] + r["walled_before"]
        price_after = r["open_after"] + r["walled_after"]
        improves = price_after < price_before or (price_after == price_before and r["open_after"] < r["open_before"])
        check(r["kept"] == improves, f"rip row breaks the keep rule: {r}")
        check(r["open_before"] == expect_open, f"rip row open_before {r[open_before]} != running open {expect_open}")
        if r["kept"]:
            expect_open = r["open_after"]
    check(expect_open == rip_open, f"kept rip rounds end at {expect_open} open, proof says {rip_open}")
    print(f"OK: baseline {base_open} open / {base_walled} walled; rip {rip_open} open / {rip_walled} walled; {len(rows_a)} rip round(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
