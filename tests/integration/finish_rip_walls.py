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
             A second board, generated in the test, walls one pad in with a ring of routed arcs so a rip
             round must actually run there: exactly one round, the four square tracks ripped, kept, and the
             connection closed (this is the coverage the hub board cannot give: its ladder completes).
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



WALLED_BOARD = """(kicad_pcb
	(version 20260206)
	(generator "pcbnew")
	(generator_version "10.0")
	(general
		(thickness 1.6)
		(legacy_teardrops no)
	)
	(paper "A4")
	(layers
		(0 "F.Cu" signal)
		(2 "B.Cu" signal)
		(9 "F.Adhes" user)
		(11 "B.Adhes" user)
		(13 "F.Paste" user)
		(15 "B.Paste" user)
		(5 "F.SilkS" user)
		(7 "B.SilkS" user)
		(1 "F.Mask" user)
		(3 "B.Mask" user)
		(17 "Dwgs.User" user)
		(19 "Cmts.User" user)
		(21 "Eco1.User" user)
		(23 "Eco2.User" user)
		(25 "Edge.Cuts" user)
		(27 "Margin" user)
		(31 "F.CrtYd" user)
		(29 "B.CrtYd" user)
		(35 "F.Fab" user)
		(33 "B.Fab" user)
	)
	(setup
		(pad_to_mask_clearance 0.0254)
	)
	(net 0 "")
	(net 1 "A")
	(net 2 "WALL")
	(footprint "Test:WalledPin"
		(layer "F.Cu")
		(uuid "11111111-1111-1111-1111-111111111111")
		(at 100 100)
		(attr smd)
		(pad "1" smd rect
			(at 0 0)
			(size 0.36 0.36)
			(layers "F.Cu" "F.Paste" "F.Mask")
			(net 1 "A")
			(uuid "11111111-1111-1111-1111-111111111112")
		)
	)
	(footprint "Test:FarPin"
		(layer "F.Cu")
		(uuid "22222222-2222-2222-2222-222222222222")
		(at 106 100)
		(attr smd)
		(pad "1" smd rect
			(at 0 0)
			(size 0.36 0.36)
			(layers "F.Cu" "F.Paste" "F.Mask")
			(net 1 "A")
			(uuid "22222222-2222-2222-2222-222222222223")
		)
	)
	(arc (start 99.5 100) (mid 100 99.5) (end 100.5 100) (width 0.3) (layer "F.Cu") (net "WALL") (uuid "33333333-3333-3333-3333-333333333331"))
	(arc (start 100.5 100) (mid 100 100.5) (end 99.5 100) (width 0.3) (layer "F.Cu") (net "WALL") (uuid "33333333-3333-3333-3333-333333333332"))
	(gr_line (start 98 98) (end 108 98) (stroke (width 0.1) (type solid)) (layer "Edge.Cuts") (uuid "44444444-4444-4444-4444-444444444441"))
	(gr_line (start 108 98) (end 108 102) (stroke (width 0.1) (type solid)) (layer "Edge.Cuts") (uuid "44444444-4444-4444-4444-444444444442"))
	(gr_line (start 108 102) (end 98 102) (stroke (width 0.1) (type solid)) (layer "Edge.Cuts") (uuid "44444444-4444-4444-4444-444444444443"))
	(gr_line (start 98 102) (end 98 98) (stroke (width 0.1) (type solid)) (layer "Edge.Cuts") (uuid "44444444-4444-4444-4444-444444444444"))
)
"""


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
        check(r["open_before"] == expect_open, f"rip row open_before {r['open_before']} != running open {expect_open}")
        if r["kept"]:
            expect_open = r["open_after"]
    check(expect_open == rip_open, f"kept rip rounds end at {expect_open} open, proof says {rip_open}")

    # A board where a rip round must actually run (the hub ladder above completes, so its rip rows are
    # empty): one connection, its first pad walled in by a ring of two routed arcs of another net. Arcs,
    # not tracks: the repair pass rips tracks and vias of other nets, so a track wall would be repaired
    # away inside the fitted rung and the rip phase would never be reached; repair never rips arcs, so
    # the ladder leaves the connection open, the rip phase proofs it, rips the two arcs, and the heal
    # closes the connection: exactly one kept round.
    wb = work / "walled.kicad_pcb"
    wb.write_text(WALLED_BOARD)
    walled_outs = []
    for tag in ("walled1", "walled2"):
        out = work / f"{tag}.kicad_pcb"
        js = work / f"{tag}.json"
        p = route(tm, wb, out, js, "--finish", "--finish-rip-walls", "--deterministic", "--work", "20000000")
        check(p.returncode == 0, f"{tag}: rc {p.returncode}: {p.stdout[-300:]} {p.stderr[-200:]}")
        s = json.loads(js.read_text())
        check(s.get("deterministic") is True, f"{tag}: summary does not claim deterministic")
        rows = [r for r in s["finish"]["rungs"] if str(r.get("rung", "")).startswith("rip walls")]
        check(len(rows) == 1, f"{tag}: expected exactly one rip round, got {rows}")
        check(rows[0]["ripped"] == 2, f"{tag}: expected the 2 wall arcs ripped, got {rows[0]}")
        check(rows[0]["kept"] is True, f"{tag}: the round must be kept: {rows[0]}")
        check(s["finish"]["open"] == 0, f"{tag}: finish open {s['finish']['open']} != 0")
        walled_outs.append(out.read_bytes())
    check(walled_outs[0] == walled_outs[1], "walled-board rip runs differ: the phase is not deterministic")
    print(f"OK: baseline {base_open} open / {base_walled} walled; rip {rip_open} open / {rip_walled} walled; {len(rows_a)} rip round(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
