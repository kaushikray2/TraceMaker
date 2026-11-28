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
"""Issue 38 item 2: a coupled pair transition may be a micro via (or a blind via over its span).

  pair_micro.py <tracemaker> <work dir>

A generated 4-layer HDI board: DP/DN pads on F.Cu at both ends, a locked wall track severing F.Cu at x = 18,
and a locked WALL band covering all of B.Cu. The pair must change layer to cross, and every through via is
blocked by the B.Cu band - so without --micro-vias the pair cannot route coupled at all. With --micro-vias
(board setup allows them) it couples on In1.Cu through micro vias F<->In1, and every via written for the pair
spans exactly F.Cu..In1.Cu.
"""
import json
import pathlib
import re
import subprocess
import sys

HEAD = """(kicad_pcb (version 20240108) (generator "pcbnew")
  (general (thickness 1.6))
  (layers (0 "F.Cu" signal) (1 "In1.Cu" signal) (2 "In2.Cu" signal) (31 "B.Cu" signal) (44 "Edge.Cuts" user))
  (setup (pad_to_mask_clearance 0) (uvias_allowed yes))
  (net 0 "") (net 2 "DP") (net 3 "DN") (net 4 "WALL")
  (gr_rect (start 0 0) (end 36 16) (stroke (width 0.1) (type default)) (fill none) (layer "Edge.Cuts"))
"""


def pad(ref, x, y, net, name):
    return (f'  (footprint "T:P" (layer "F.Cu") (at {x} {y}) (property "Reference" "{ref}")\n'
            f'    (pad "1" smd rect (at 0 0) (size 1 0.3) (layers "F.Cu") (net {net} "{name}")))\n')


WALL_F = '  (segment (start 18 0) (end 18 16) (width 0.5) (locked yes) (layer "F.Cu") (net 4))\n'
WALL_B = '  (segment (start 0 8) (end 36 8) (width 16) (locked yes) (layer "B.Cu") (net 4))\n'

BOARD = (HEAD + pad("J1", 3, 7.725, 2, "DP") + pad("J2", 3, 8.275, 3, "DN") +
         pad("J3", 33, 7.725, 2, "DP") + pad("J4", 33, 8.275, 3, "DN") + WALL_F + WALL_B + ")\n")

VIA = re.compile(r"\(via(?:\s+(micro|blind|buried))?\s+\(at [\d.]+ [\d.]+\)\s+\(size ([\d.]+)\)\s+\(drill ([\d.]+)\)\s+\(layers ([^)]*)\)\s+\(net ([23])\)")

errors = []


def check(cond, text):
    if not cond:
        errors.append(text)


def route(tm, src, out, extra):
    js = pathlib.Path(str(out) + ".json")
    r = subprocess.run([str(tm), "route", str(src), "-o", str(out), "--json", str(js), "--diff-pairs",
                        "--work", "2000000", "--variants", "1", "--threads", "1", "--no-kb", "--no-gpu"] + extra,
                       capture_output=True, text=True)
    if r.returncode not in (0, 3):
        sys.exit(f"{out.name}: tracemaker failed\n{r.stdout[-1500:]}\n{r.stderr[-1500:]}")
    return json.loads(js.read_text())


def coupled(res):
    pairs = res.get("pairs", [])
    return len(pairs) == 1 and pairs[0]["coupled_share"] >= 0.8 and res["routed"] == res["connections"]


def main() -> int:
    tm, work = sys.argv[1], pathlib.Path(sys.argv[2])
    work.mkdir(parents=True, exist_ok=True)
    src = work / "pair_micro.kicad_pcb"
    src.write_text(BOARD)
    plain = route(tm, src, work / "plain.kicad_pcb", [])
    check(not coupled(plain), f"without --micro-vias the pair must not couple: {plain.get('pairs')}, routed {plain['routed']}/{plain['connections']}")
    micro_out = work / "micro.kicad_pcb"
    micro = route(tm, src, micro_out, ["--micro-vias"])
    check(coupled(micro), f"with --micro-vias the pair must couple: {micro.get('pairs')}, routed {micro['routed']}/{micro['connections']}")
    vias = VIA.findall(micro_out.read_text())
    check(len(vias) >= 4, f"expected at least 4 pair vias (2 transitions x 2 halves), got {len(vias)}")
    for vtype, size, drill, layers, net in vias:
        check(vtype == "micro", f"pair via on net {net} is {vtype or 'through'}, not micro")
        check(layers.strip() == '"F.Cu" "In1.Cu"', f"pair via on net {net} spans {layers}, not the micro span F.Cu..In1.Cu")
        check(abs(float(size) - 0.3) < 1e-6, f"pair via size {size}, not the micro diameter 0.3")
    print(f"micro vias for the pair: {len(vias)}; coupled_share {micro['pairs'][0]['coupled_share']:.2f}")
    if errors:
        print("FAIL:", "; ".join(errors))
        return 1
    print("pair_micro: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
