#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
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
"""ClassCache sharing across a tuning-profile class (issue 59).

  cache_profile.py <tracemaker> <work dir>

Two classes with IDENTICAL scalars (track 0.30, clearance 0.20, via 0.6/0.3):
Default, and PROF whose nets name single-ended tuning profile P1 (In1.Cu width
0.15). width_on reads the profile's per-layer widths, so the two classes must
never share a ClassCache: the cached fixed-copper codes are computed at the
first net's half-width and would be read back as legality at the wrong width.
(The cache separation itself is pinned directly by the obstacle-caches unit
test in tests/test_design_rules.cpp, which builds its rules by hand; through
the project reader, add_tuning_rules' implicit hasExactNetclass rules also
force per-class caches. This fixture pins the routed outcome end to end.)

Board (4 layers): DEF (Default) and SIG (PROF) both aim at the same 0.6 mm
slot between BLOCK rails on In1.Cu (the perlayer_widths slot). DEF has no
legal crossing of its own (the slot is too narrow at its scalar 0.30 mm and
In2.Cu/B.Cu are keepout-covered), so it stays open. SIG, whose profile width
on In1.Cu is 0.15 mm, fits the slot with clearance to spare - at its own
per-layer width, judged by its own class's codes.

Checks: SIG crosses the slot on In1.Cu at 0.15 mm and is the one routed
connection of the two; DEF has no In1.Cu segment inside the slot span.
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
	(net 2 "DEF")
	(net 3 "BLOCK")
	(footprint "Test:D1" (layer "F.Cu") (uuid "00000000-0000-0000-0000-000000000011") (at 99.3 100) (attr smd) (pad "1" smd rect (at 0 0) (size 0.6 0.6) (layers "F.Cu" "F.Paste" "F.Mask") (net 2 "DEF") (uuid "00000000-0000-0000-0000-000000000012")))
	(footprint "Test:D2" (layer "F.Cu") (uuid "00000000-0000-0000-0000-000000000013") (at 106.7 100) (attr smd) (pad "1" smd rect (at 0 0) (size 0.6 0.6) (layers "F.Cu" "F.Paste" "F.Mask") (net 2 "DEF") (uuid "00000000-0000-0000-0000-000000000014")))
	(footprint "Test:S1" (layer "F.Cu") (uuid "00000000-0000-0000-0000-000000000001") (at 100.3 100.3) (attr smd) (pad "1" smd rect (at 0 0) (size 0.8 0.8) (layers "F.Cu" "F.Paste" "F.Mask") (net 1 "SIG") (uuid "00000000-0000-0000-0000-000000000002")))
	(footprint "Test:S2" (layer "F.Cu") (uuid "00000000-0000-0000-0000-000000000003") (at 105.7 100.3) (attr smd) (pad "1" smd rect (at 0 0) (size 0.8 0.8) (layers "F.Cu" "F.Paste" "F.Mask") (net 1 "SIG") (uuid "00000000-0000-0000-0000-000000000004")))
"""
RAILS = [(98.0, 98.6), (100.0, 100.3), (101.5, 104.5), (105.7, 106.2), (107.4, 108.5)]
u = 41
for y in (99.575, 100.425):
    for x0, x1 in RAILS:
        BOARD += '\t(segment (start %s %s) (end %s %s) (width 0.25) (layer "In1.Cu") (net 3) (uuid "00000000-0000-0000-0000-%012d"))\n' % (x0, y, x1, y, u)
        u += 1
ZONE = '\t(zone (net 0) (net_name "") (layer "{layer}") (uuid "00000000-0000-0000-0000-{uuid:012d}") (hatch edge 0.5) (connect_pads (clearance 0)) (min_thickness 0.25) (filled_areas_thickness no) (keepout (tracks not_allowed) (vias {vias}) (pads allowed) (copperpour not_allowed) (footprints allowed)) (fill (thermal_gap 0.5) (thermal_bridge_width 0.5)) (polygon (pts {pts})))\n'
ZONES = [
    ("F.Cu", "not_allowed", (96, 96, 108, 98.9)),
    ("F.Cu", "not_allowed", (96, 101.1, 108, 104)),
    ("F.Cu", "not_allowed", (96, 98.9, 98.9, 101.1)),
    ("F.Cu", "not_allowed", (101.1, 98.9, 104.9, 101.1)),
    ("F.Cu", "not_allowed", (107.1, 98.9, 108, 101.1)),
    ("In1.Cu", "not_allowed", (96, 96, 108, 99.3)),
    ("In1.Cu", "not_allowed", (96, 100.7, 108, 104)),
    ("In1.Cu", "not_allowed", (96, 99.3, 98.9, 100.7)),
    ("In1.Cu", "not_allowed", (107.1, 99.3, 108, 100.7)),
    ("In1.Cu", "not_allowed", (101.5, 99.3, 104.5, 99.7)),
    ("In1.Cu", "not_allowed", (101.5, 100.3, 104.5, 100.7)),
    ("In2.Cu", "allowed", (96, 96, 108, 104)),
    ("B.Cu", "allowed", (96, 96, 108, 104)),
]
for i, (layer, vias, (x0, y0, x1, y1)) in enumerate(ZONES):
    pts = "(xy %s %s) (xy %s %s) (xy %s %s) (xy %s %s)" % (x0, y0, x1, y0, x1, y1, x0, y1)
    BOARD += ZONE.format(layer=layer, uuid=61 + i, vias=vias, pts=pts)
BOARD += ")\n"

PRO = {
    "board": {"design_settings": {"rules": {"min_track_width": 0.1, "min_clearance": 0.1}}},
    "net_settings": {
        "classes": [
            {"name": "Default", "clearance": 0.2, "track_width": 0.3, "via_diameter": 0.6, "via_drill": 0.3},
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


def segs(text, net):
    out = []
    for chunk in text.split("(segment")[1:]:
        seg = chunk[:500]
        n = re.search(r"\(net (\d+)\)", seg)
        if not n or int(n.group(1)) != net:
            continue
        layer = re.search(r'\(layer "([^"]+)"\)', seg).group(1)
        width = float(re.search(r"\(width ([\d.]+)\)", seg).group(1))
        st = re.search(r"\(start ([\d.]+) ([\d.]+)\)", seg)
        en = re.search(r"\(end ([\d.]+) ([\d.]+)\)", seg)
        out.append((layer, width, float(st.group(1)), float(st.group(2)), float(en.group(1)), float(en.group(2))))
    return out


def main() -> int:
    tm, work = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
    work.mkdir(parents=True, exist_ok=True)
    src = work / "cacheprof.kicad_pcb"
    src.write_text(BOARD)
    (work / "cacheprof.kicad_pro").write_text(json.dumps(PRO))
    out = work / "cacheprof-out.kicad_pcb"
    js = work / "cacheprof.json"
    r = subprocess.run([str(tm), "route", str(src), "--no-gpu", "--deterministic", "--work", "2000000", "--repair", "off",
                        "-o", str(out), "--json", str(js)], capture_output=True, text=True)
    if r.returncode not in (0, 3):
        print(r.stdout[-1500:], r.stderr[-1500:])
        return 1
    summary = json.loads(js.read_text())
    errors = []
    if "tuning_profiles" not in summary:
        errors.append("route JSON names no tuning profiles: the project file was not read")
    if summary.get("connections", 0) != 2 or summary.get("routed") != 1:
        errors.append("expected exactly SIG routed of 2 connections: %s/%s" % (summary.get("routed"), summary.get("connections")))
    text = out.read_text() if out.exists() else ""
    sig_in1 = [s for s in segs(text, 1) if s[0] == "In1.Cu"]
    if not sig_in1:
        errors.append("SIG has no segment on In1.Cu: the slot was not crossed")
    for s in sig_in1:
        if abs(s[1] - 0.15) > 1e-6:
            errors.append("SIG In1.Cu segment width %s != 0.15 (the profile per-layer width)" % s[1])
    for s in segs(text, 2):
        if s[0] == "In1.Cu":
            mx, my = (s[2] + s[4]) / 2, (s[3] + s[5]) / 2
            if 101.0 <= mx <= 105.0 and 99.6 <= my <= 100.4:
                errors.append("DEF has an In1.Cu segment inside the slot span (mid %.2f,%.2f): it crossed at a width the slot forbids" % (mx, my))
    for e in errors:
        print("FAIL:", e)
    if not errors:
        print("cache/profile: SIG crossed the In1.Cu slot at 0.15 mm at its own profile width, caches stayed per-class")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
