# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SiliconBrane Inc.
"""Issue 30: the chains clique solver's contract on a board with no qualifying failure.

Two halves. On the hub fixture (whose chains baseline leaves nothing open) the clique
must be inert: identical tallies with the solver on and off, the options echo carrying
the clique fields with their defaults, and byte-stable JSON across two runs. The live
fire runs on the inline synthetic board below (issue 53): three nets in three
single-track channels, arranged so the chain fails as lifted_net_no_path_bare at the
default depth and too_deep at --max-depth 2, and only the clique closes it - the hub
cannot produce a qualifying failure at any setting probed, and the fixture is
untracked in side worktrees. Sizif's too_deep closing as closed_clique with every
other tally unchanged is the real-board evidence, recorded on issue 30.

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


CLIQUE_BOARD = r"""(kicad_pcb
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
	(net 2 "B")
	(net 3 "C")
	(footprint "Test:A1" (layer "F.Cu") (uuid "00000000-0000-0000-0000-000000000001") (at 98.5 100) (attr smd) (pad "1" smd rect (at 0 0) (size 0.5 0.5) (layers "F.Cu" "F.Paste" "F.Mask") (net 1 "A") (uuid "00000000-0000-0000-0000-000000000002")))
	(footprint "Test:A2" (layer "F.Cu") (uuid "00000000-0000-0000-0000-000000000003") (at 105.5 100) (attr smd) (pad "1" smd rect (at 0 0) (size 0.5 0.5) (layers "F.Cu" "F.Paste" "F.Mask") (net 1 "A") (uuid "00000000-0000-0000-0000-000000000004")))
	(footprint "Test:B1" (layer "F.Cu") (uuid "00000000-0000-0000-0000-000000000005") (at 100 101.4) (attr smd) (pad "1" smd rect (at 0 0) (size 0.5 0.5) (layers "F.Cu" "F.Paste" "F.Mask") (net 2 "B") (uuid "00000000-0000-0000-0000-000000000006")))
	(footprint "Test:B2" (layer "F.Cu") (uuid "00000000-0000-0000-0000-000000000007") (at 104 101.4) (attr smd) (pad "1" smd rect (at 0 0) (size 0.5 0.5) (layers "F.Cu" "F.Paste" "F.Mask") (net 2 "B") (uuid "00000000-0000-0000-0000-000000000008")))
	(footprint "Test:C1" (layer "F.Cu") (uuid "00000000-0000-0000-0000-000000000009") (at 101 102.6) (attr smd) (pad "1" smd rect (at 0 0) (size 0.5 0.5) (layers "F.Cu" "F.Paste" "F.Mask") (net 3 "C") (uuid "00000000-0000-0000-0000-000000000010")))
	(footprint "Test:C2" (layer "F.Cu") (uuid "00000000-0000-0000-0000-000000000011") (at 103 102.6) (attr smd) (pad "1" smd rect (at 0 0) (size 0.5 0.5) (layers "F.Cu" "F.Paste" "F.Mask") (net 3 "C") (uuid "00000000-0000-0000-0000-000000000012")))
	(segment (start 100 101.4) (end 100 100) (width 0.25) (layer "F.Cu") (net 2) (uuid "00000000-0000-0000-0000-000000000013"))
	(segment (start 100 100) (end 104 100) (width 0.25) (layer "F.Cu") (net 2) (uuid "00000000-0000-0000-0000-000000000014"))
	(segment (start 104 100) (end 104 101.4) (width 0.25) (layer "F.Cu") (net 2) (uuid "00000000-0000-0000-0000-000000000015"))
	(segment (start 101 102.6) (end 101 102) (width 0.25) (layer "F.Cu") (net 3) (uuid "00000000-0000-0000-0000-000000000016"))
	(segment (start 101 102) (end 102 102) (width 0.25) (layer "F.Cu") (net 3) (uuid "00000000-0000-0000-0000-000000000017"))
	(segment (start 102 102) (end 103 102) (width 0.25) (layer "F.Cu") (net 3) (uuid "00000000-0000-0000-0000-000000000018"))
	(segment (start 103 102) (end 103 102.6) (width 0.25) (layer "F.Cu") (net 3) (uuid "00000000-0000-0000-0000-000000000019"))
	(segment (start 102 102) (end 102 104) (width 0.25) (layer "F.Cu") (net 3) (uuid "00000000-0000-0000-0000-000000000020"))
	(zone (net 0) (net_name "") (layer "F.Cu") (uuid "00000000-0000-0000-0000-000000000021") (hatch edge 0.5) (connect_pads (clearance 0)) (min_thickness 0.25) (filled_areas_thickness no) (keepout (tracks not_allowed) (vias not_allowed) (pads allowed) (copperpour not_allowed) (footprints allowed)) (fill (thermal_gap 0.5) (thermal_bridge_width 0.5)) (polygon (pts (xy 96 96) (xy 108 96) (xy 108 99.75) (xy 96 99.75))))
	(zone (net 0) (net_name "") (layer "F.Cu") (uuid "00000000-0000-0000-0000-000000000022") (hatch edge 0.5) (connect_pads (clearance 0)) (min_thickness 0.25) (filled_areas_thickness no) (keepout (tracks not_allowed) (vias not_allowed) (pads allowed) (copperpour not_allowed) (footprints allowed)) (fill (thermal_gap 0.5) (thermal_bridge_width 0.5)) (polygon (pts (xy 96 104.25) (xy 108 104.25) (xy 108 107) (xy 96 107))))
	(zone (net 0) (net_name "") (layer "F.Cu") (uuid "00000000-0000-0000-0000-000000000023") (hatch edge 0.5) (connect_pads (clearance 0)) (min_thickness 0.25) (filled_areas_thickness no) (keepout (tracks not_allowed) (vias not_allowed) (pads allowed) (copperpour not_allowed) (footprints allowed)) (fill (thermal_gap 0.5) (thermal_bridge_width 0.5)) (polygon (pts (xy 96 100.25) (xy 98.17 100.25) (xy 98.17 101.75) (xy 96 101.75))))
	(zone (net 0) (net_name "") (layer "F.Cu") (uuid "00000000-0000-0000-0000-000000000024") (hatch edge 0.5) (connect_pads (clearance 0)) (min_thickness 0.25) (filled_areas_thickness no) (keepout (tracks not_allowed) (vias not_allowed) (pads allowed) (copperpour not_allowed) (footprints allowed)) (fill (thermal_gap 0.5) (thermal_bridge_width 0.5)) (polygon (pts (xy 98.83 100.25) (xy 99.6 100.25) (xy 99.6 101.75) (xy 98.83 101.75))))
	(zone (net 0) (net_name "") (layer "F.Cu") (uuid "00000000-0000-0000-0000-000000000025") (hatch edge 0.5) (connect_pads (clearance 0)) (min_thickness 0.25) (filled_areas_thickness no) (keepout (tracks not_allowed) (vias not_allowed) (pads allowed) (copperpour not_allowed) (footprints allowed)) (fill (thermal_gap 0.5) (thermal_bridge_width 0.5)) (polygon (pts (xy 100.4 100.25) (xy 103.6 100.25) (xy 103.6 101.75) (xy 100.4 101.75))))
	(zone (net 0) (net_name "") (layer "F.Cu") (uuid "00000000-0000-0000-0000-000000000026") (hatch edge 0.5) (connect_pads (clearance 0)) (min_thickness 0.25) (filled_areas_thickness no) (keepout (tracks not_allowed) (vias not_allowed) (pads allowed) (copperpour not_allowed) (footprints allowed)) (fill (thermal_gap 0.5) (thermal_bridge_width 0.5)) (polygon (pts (xy 104.4 100.25) (xy 105.17 100.25) (xy 105.17 101.75) (xy 104.4 101.75))))
	(zone (net 0) (net_name "") (layer "F.Cu") (uuid "00000000-0000-0000-0000-000000000027") (hatch edge 0.5) (connect_pads (clearance 0)) (min_thickness 0.25) (filled_areas_thickness no) (keepout (tracks not_allowed) (vias not_allowed) (pads allowed) (copperpour not_allowed) (footprints allowed)) (fill (thermal_gap 0.5) (thermal_bridge_width 0.5)) (polygon (pts (xy 105.83 100.25) (xy 108 100.25) (xy 108 101.75) (xy 105.83 101.75))))
	(zone (net 0) (net_name "") (layer "F.Cu") (uuid "00000000-0000-0000-0000-000000000028") (hatch edge 0.5) (connect_pads (clearance 0)) (min_thickness 0.25) (filled_areas_thickness no) (keepout (tracks not_allowed) (vias not_allowed) (pads allowed) (copperpour not_allowed) (footprints allowed)) (fill (thermal_gap 0.5) (thermal_bridge_width 0.5)) (polygon (pts (xy 96 102.25) (xy 98.17 102.25) (xy 98.17 103) (xy 96 103))))
	(zone (net 0) (net_name "") (layer "F.Cu") (uuid "00000000-0000-0000-0000-000000000029") (hatch edge 0.5) (connect_pads (clearance 0)) (min_thickness 0.25) (filled_areas_thickness no) (keepout (tracks not_allowed) (vias not_allowed) (pads allowed) (copperpour not_allowed) (footprints allowed)) (fill (thermal_gap 0.5) (thermal_bridge_width 0.5)) (polygon (pts (xy 98.83 102.25) (xy 100.6 102.25) (xy 100.6 103) (xy 98.83 103))))
	(zone (net 0) (net_name "") (layer "F.Cu") (uuid "00000000-0000-0000-0000-000000000030") (hatch edge 0.5) (connect_pads (clearance 0)) (min_thickness 0.25) (filled_areas_thickness no) (keepout (tracks not_allowed) (vias not_allowed) (pads allowed) (copperpour not_allowed) (footprints allowed)) (fill (thermal_gap 0.5) (thermal_bridge_width 0.5)) (polygon (pts (xy 101.4 102.25) (xy 101.67 102.25) (xy 101.67 103) (xy 101.4 103))))
	(zone (net 0) (net_name "") (layer "F.Cu") (uuid "00000000-0000-0000-0000-000000000031") (hatch edge 0.5) (connect_pads (clearance 0)) (min_thickness 0.25) (filled_areas_thickness no) (keepout (tracks not_allowed) (vias not_allowed) (pads allowed) (copperpour not_allowed) (footprints allowed)) (fill (thermal_gap 0.5) (thermal_bridge_width 0.5)) (polygon (pts (xy 102.33 102.25) (xy 102.6 102.25) (xy 102.6 103) (xy 102.33 103))))
	(zone (net 0) (net_name "") (layer "F.Cu") (uuid "00000000-0000-0000-0000-000000000032") (hatch edge 0.5) (connect_pads (clearance 0)) (min_thickness 0.25) (filled_areas_thickness no) (keepout (tracks not_allowed) (vias not_allowed) (pads allowed) (copperpour not_allowed) (footprints allowed)) (fill (thermal_gap 0.5) (thermal_bridge_width 0.5)) (polygon (pts (xy 103.4 102.25) (xy 105.17 102.25) (xy 105.17 103) (xy 103.4 103))))
	(zone (net 0) (net_name "") (layer "F.Cu") (uuid "00000000-0000-0000-0000-000000000033") (hatch edge 0.5) (connect_pads (clearance 0)) (min_thickness 0.25) (filled_areas_thickness no) (keepout (tracks not_allowed) (vias not_allowed) (pads allowed) (copperpour not_allowed) (footprints allowed)) (fill (thermal_gap 0.5) (thermal_bridge_width 0.5)) (polygon (pts (xy 105.83 102.25) (xy 108 102.25) (xy 108 103) (xy 105.83 103))))
	(zone (net 0) (net_name "") (layer "F.Cu") (uuid "00000000-0000-0000-0000-000000000034") (hatch edge 0.5) (connect_pads (clearance 0)) (min_thickness 0.25) (filled_areas_thickness no) (keepout (tracks not_allowed) (vias not_allowed) (pads allowed) (copperpour not_allowed) (footprints allowed)) (fill (thermal_gap 0.5) (thermal_bridge_width 0.5)) (polygon (pts (xy 96 103) (xy 98.17 103) (xy 98.17 103.75) (xy 96 103.75))))
	(zone (net 0) (net_name "") (layer "F.Cu") (uuid "00000000-0000-0000-0000-000000000035") (hatch edge 0.5) (connect_pads (clearance 0)) (min_thickness 0.25) (filled_areas_thickness no) (keepout (tracks not_allowed) (vias not_allowed) (pads allowed) (copperpour not_allowed) (footprints allowed)) (fill (thermal_gap 0.5) (thermal_bridge_width 0.5)) (polygon (pts (xy 98.83 103) (xy 101.67 103) (xy 101.67 103.75) (xy 98.83 103.75))))
	(zone (net 0) (net_name "") (layer "F.Cu") (uuid "00000000-0000-0000-0000-000000000036") (hatch edge 0.5) (connect_pads (clearance 0)) (min_thickness 0.25) (filled_areas_thickness no) (keepout (tracks not_allowed) (vias not_allowed) (pads allowed) (copperpour not_allowed) (footprints allowed)) (fill (thermal_gap 0.5) (thermal_bridge_width 0.5)) (polygon (pts (xy 102.33 103) (xy 105.17 103) (xy 105.17 103.75) (xy 102.33 103.75))))
	(zone (net 0) (net_name "") (layer "F.Cu") (uuid "00000000-0000-0000-0000-000000000037") (hatch edge 0.5) (connect_pads (clearance 0)) (min_thickness 0.25) (filled_areas_thickness no) (keepout (tracks not_allowed) (vias not_allowed) (pads allowed) (copperpour not_allowed) (footprints allowed)) (fill (thermal_gap 0.5) (thermal_bridge_width 0.5)) (polygon (pts (xy 105.83 103) (xy 108 103) (xy 108 103.75) (xy 105.83 103.75))))
	(zone (net 0) (net_name "") (layer "B.Cu") (uuid "00000000-0000-0000-0000-000000000038") (hatch edge 0.5) (connect_pads (clearance 0)) (min_thickness 0.25) (filled_areas_thickness no) (keepout (tracks not_allowed) (vias not_allowed) (pads allowed) (copperpour not_allowed) (footprints allowed)) (fill (thermal_gap 0.5) (thermal_bridge_width 0.5)) (polygon (pts (xy 96 96) (xy 108 96) (xy 108 107) (xy 96 107))))
	(gr_line (start 96 96) (end 108 96) (stroke (width 0.1) (type solid)) (layer "Edge.Cuts") (uuid "00000000-0000-0000-0000-000000000039"))
	(gr_line (start 108 96) (end 108 107) (stroke (width 0.1) (type solid)) (layer "Edge.Cuts") (uuid "00000000-0000-0000-0000-000000000040"))
	(gr_line (start 108 107) (end 96 107) (stroke (width 0.1) (type solid)) (layer "Edge.Cuts") (uuid "00000000-0000-0000-0000-000000000041"))
	(gr_line (start 96 107) (end 96 96) (stroke (width 0.1) (type solid)) (layer "Edge.Cuts") (uuid "00000000-0000-0000-0000-000000000042"))
)
"""


def chains_on(tm, work, tag, board, *extra):
    js = work / f"{tag}.json"
    p = subprocess.run([str(tm), "chains", str(board), "--json", str(js), *extra],
                       capture_output=True, text=True)
    check(p.returncode == 0, f"{tag}: chains rc {p.returncode}: {p.stdout[-300:]} {p.stderr[-200:]}")
    return json.loads(js.read_text())


def synthetic_checks(tm, work):
    board = work / "clique_board.kicad_pcb"
    board.write_text(CLIQUE_BOARD)
    on = chains_on(tm, work, "synth_on", board)
    check(on.get("tally") == {"closed_clique": 1}, f"synthetic clique-on tally: {on.get('tally')}")
    row = on["connections"][0]
    check(row.get("clique_tried") is True and row.get("clique_nets") == 3 and row.get("closed") is True,
          f"synthetic clique row: {row}")
    off = chains_on(tm, work, "synth_off", board, "--no-clique")
    check(off.get("tally") == {"lifted_net_no_path_bare": 1}, f"synthetic clique-off tally: {off.get('tally')}")
    check(off["connections"][0].get("closed") is False, "synthetic board closed with the clique off")
    deep = chains_on(tm, work, "synth_deep", board, "--no-clique", "--max-depth", "2")
    check(deep.get("tally") == {"too_deep": 1}, f"synthetic depth-2 tally: {deep.get('tally')}")
    on2 = chains_on(tm, work, "synth_on2", board, "--max-depth", "2")
    check(on2.get("tally") == {"closed_clique": 1}, f"synthetic depth-2 clique tally: {on2.get('tally')}")
    out = work / "synth_out.kicad_pcb"
    ap_js = work / "synth_apply.json"
    p = subprocess.run([str(tm), "chains", str(board), "--apply", str(out), "--json", str(ap_js)],
                       capture_output=True, text=True)
    check(p.returncode == 0, f"synthetic apply rc {p.returncode}: {p.stdout[-300:]} {p.stderr[-200:]}")
    applied = json.loads(ap_js.read_text()).get("applied", {})
    check(applied.get("written") is True and applied.get("open_after") == 0, f"synthetic apply: {applied}")


def main():
    tm, work = sys.argv[1], pathlib.Path(sys.argv[2])
    work.mkdir(parents=True, exist_ok=True)
    synthetic_checks(tm, work)
    if not SRC.exists():
        print(f"fixture missing: {SRC} (synthetic clique checks passed; hub inertness skipped)")
        return 0

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
    print("PASS chains_clique: synthetic live fire (issue 53) + options echo, inertness and stability on the hub fixture")
    return 0


if __name__ == "__main__":
    sys.exit(main())
