#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SiliconBrane Inc.
"""Per-layer track widths (issue 37, 3C-1), end to end through a tuning profile.

  perlayer_widths.py <tracemaker> <work dir>

A synthetic 4-layer board: net SIG has two pads in pockets on F.Cu; every layer except
In1.Cu is keepout-covered, and on In1.Cu two foreign tracks (net BLOCK, with gaps at the
via landings) form a slot 0.6 mm wide between their edges. SIG must via down, run the
slot on In1.Cu, and via back up. The project puts SIG in class PROF (scalar track width
0.30 mm) naming tuning profile P1, whose In1.Cu entry is 0.15 mm. SIG needs its width
plus the 0.2 mm clearance on both sides of the slot: 0.55 mm at the profile width,
0.70 mm at the scalar - so a search that probes at the scalar width (the pre-3C-1
behaviour for class maps, and for profiles the widest-first search) cannot cross the
slot at all, and the post-route narrowing pass has nothing to rescue. The route runs
with --repair off: the repair pass would lift the BLOCK rails and rescue even a scalar
search, which is its job in production but would mask the behaviour under test here.

Checks:
  * the route closes and the project was actually read (the JSON names the profile);
  * every SIG segment on In1.Cu is stamped 0.15 mm, the profile per-layer width;
  * F.Cu pocket stubs are stamped 0.30 mm; no SIG segment on In2.Cu or B.Cu.
"""
import json
import pathlib
import re
import subprocess
import sys

BOARD = r"""(kicad_pcb
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
		(1 "In1.Cu" signal)
		(2 "In2.Cu" signal)
		(31 "B.Cu" signal)
		(41 "F.Adhes" user)
		(33 "B.Adhes" user)
		(43 "F.Paste" user)
		(35 "B.Paste" user)
		(45 "F.SilkS" user)
		(37 "B.SilkS" user)
		(47 "F.Mask" user)
		(39 "B.Mask" user)
		(49 "Dwgs.User" user)
		(51 "Cmts.User" user)
		(53 "Eco1.User" user)
		(55 "Eco2.User" user)
		(57 "Edge.Cuts" user)
		(59 "Margin" user)
		(63 "F.CrtYd" user)
		(61 "B.CrtYd" user)
		(67 "F.Fab" user)
		(65 "B.Fab" user)
	)
	(setup
		(pad_to_mask_clearance 0.0254)
	)
	(net 0 "")
	(net 1 "SIG")
	(net 2 "BLOCK")
	(footprint "Test:S1" (layer "F.Cu") (uuid "00000000-0000-0000-0000-000000000001") (at 100 100) (attr smd) (pad "1" smd rect (at 0 0) (size 1 1) (layers "F.Cu" "F.Paste" "F.Mask") (net 1 "SIG") (uuid "00000000-0000-0000-0000-000000000002")))
	(footprint "Test:S2" (layer "F.Cu") (uuid "00000000-0000-0000-0000-000000000003") (at 106 100) (attr smd) (pad "1" smd rect (at 0 0) (size 1 1) (layers "F.Cu" "F.Paste" "F.Mask") (net 1 "SIG") (uuid "00000000-0000-0000-0000-000000000004")))
	(segment (start 99.3 99.575) (end 99.8 99.575) (width 0.25) (layer "In1.Cu") (net 2) (uuid "00000000-0000-0000-0000-000000000041"))
	(segment (start 100.9 99.575) (end 105.1 99.575) (width 0.25) (layer "In1.Cu") (net 2) (uuid "00000000-0000-0000-0000-000000000042"))
	(segment (start 106.2 99.575) (end 106.7 99.575) (width 0.25) (layer "In1.Cu") (net 2) (uuid "00000000-0000-0000-0000-000000000043"))
	(segment (start 99.3 100.425) (end 99.8 100.425) (width 0.25) (layer "In1.Cu") (net 2) (uuid "00000000-0000-0000-0000-000000000044"))
	(segment (start 100.9 100.425) (end 105.1 100.425) (width 0.25) (layer "In1.Cu") (net 2) (uuid "00000000-0000-0000-0000-000000000045"))
	(segment (start 106.2 100.425) (end 106.7 100.425) (width 0.25) (layer "In1.Cu") (net 2) (uuid "00000000-0000-0000-0000-000000000046"))
"""
ZONE = '\t(zone (net 0) (net_name "") (layer "{layer}") (uuid "00000000-0000-0000-0000-{uuid:012d}") (hatch edge 0.5) (connect_pads (clearance 0)) (min_thickness 0.25) (filled_areas_thickness no) (keepout (tracks not_allowed) (vias {vias}) (pads allowed) (copperpour not_allowed) (footprints allowed)) (fill (thermal_gap 0.5) (thermal_bridge_width 0.5)) (polygon (pts {pts})))\n'
ZONES = [
    ("F.Cu", "not_allowed", (96, 96, 108, 98.9)),
    ("F.Cu", "not_allowed", (96, 101.1, 108, 104)),
    ("F.Cu", "not_allowed", (96, 98.9, 99.3, 101.1)),
    ("F.Cu", "not_allowed", (100.7, 98.9, 105.3, 101.1)),
    ("F.Cu", "not_allowed", (106.7, 98.9, 108, 101.1)),
    ("In1.Cu", "not_allowed", (96, 96, 108, 99.3)),
    ("In1.Cu", "not_allowed", (96, 100.7, 108, 104)),
    ("In1.Cu", "not_allowed", (96, 99.3, 99.3, 100.7)),
    ("In1.Cu", "not_allowed", (106.7, 99.3, 108, 100.7)),
    ("In1.Cu", "not_allowed", (100.9, 99.3, 105.1, 99.7)),
    ("In1.Cu", "not_allowed", (100.9, 100.3, 105.1, 100.7)),
    ("In2.Cu", "allowed", (96, 96, 108, 104)),
    ("B.Cu", "allowed", (96, 96, 108, 104)),
]
for i, (layer, vias, (x0, y0, x1, y1)) in enumerate(ZONES):
    pts = f"(xy {x0} {y0}) (xy {x1} {y0}) (xy {x1} {y1}) (xy {x0} {y1})"
    BOARD += ZONE.format(layer=layer, uuid=21 + i, vias=vias, pts=pts)
BOARD += ")\n"

PRO = {
    "board": {"design_settings": {"rules": {"min_track_width": 0.1, "min_clearance": 0.1}}},
    "net_settings": {
        "classes": [
            {"name": "Default", "clearance": 0.2, "track_width": 0.25, "via_diameter": 0.6, "via_drill": 0.3},
            {"name": "PROF", "clearance": 0.2, "track_width": 0.3, "via_diameter": 0.6, "via_drill": 0.3, "tuning_profile": "P1"},
        ],
        "netclass_patterns": [{"pattern": "SIG", "netclass": "PROF"}],
    },
    "tuning_profiles": {
        "tuning_profiles_impedance_geometric": [
            {
                "profile_name": "P1",
                "type": 0,
                "layer_entries": [
                    {"signal_layer": "F.Cu", "width": 300000},
                    {"signal_layer": "In1.Cu", "width": 150000},
                    {"signal_layer": "In2.Cu", "width": 300000},
                    {"signal_layer": "B.Cu", "width": 300000},
                ],
            }
        ]
    },
}


def main() -> int:
    tm, work = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
    work.mkdir(parents=True, exist_ok=True)
    src = work / "perlayer.kicad_pcb"
    src.write_text(BOARD)
    (work / "perlayer.kicad_pro").write_text(json.dumps(PRO))
    out = work / "perlayer-out.kicad_pcb"
    js = work / "perlayer.json"
    r = subprocess.run([str(tm), "route", str(src), "--no-gpu", "--deterministic", "--work", "2000000", "--repair", "off",
                        "-o", str(out), "--json", str(js)], capture_output=True, text=True)
    if r.returncode not in (0, 3):
        print(r.stdout[-1500:], r.stderr[-1500:])
        return 1
    summary = json.loads(js.read_text())
    errors = []
    if "tuning_profiles" not in summary:
        errors.append("route JSON names no tuning profiles: the project file was not read")
    if summary.get("routed") != summary.get("connections") or summary.get("connections", 0) < 1:
        errors.append(f"route did not close: {summary.get('routed')}/{summary.get('connections')}")
    text = out.read_text() if out.exists() else ""
    in1_widths = []
    other_layers = []
    for chunk in text.split("(segment")[1:]:
        seg = chunk[:400]
        net = re.search(r"\(net (\d+)\)", seg)
        if not net or int(net.group(1)) != 1:
            continue
        layer = re.search(r'\(layer "([^"]+)"\)', seg).group(1)
        width = float(re.search(r"\(width ([\d.]+)\)", seg).group(1))
        (in1_widths if layer == "In1.Cu" else other_layers).append((layer, width))
    if not in1_widths:
        errors.append("SIG has no segment on In1.Cu: the slot was not crossed")
    for layer, width in in1_widths:
        if abs(width - 0.15) > 1e-6:
            errors.append(f"In1.Cu segment width {width} != 0.15 (the profile per-layer width)")
    for layer, width in other_layers:
        if layer == "F.Cu":
            if abs(width - 0.30) > 1e-6:
                errors.append(f"F.Cu stub width {width} != 0.30 (the profile F.Cu width)")
        else:
            errors.append(f"SIG segment on forbidden layer {layer} (width {width})")
    for e in errors:
        print("FAIL:", e)
    if not errors:
        print(f"per-layer widths: SIG crossed the In1.Cu slot at 0.15 mm ({len(in1_widths)} segments), scalar was 0.30")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
