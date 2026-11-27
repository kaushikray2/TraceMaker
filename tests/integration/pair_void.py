#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Issue 38 item 1: a critical differential pair is charged for running over a void of its reference plane.

  pair_void.py <tracemaker> <work dir>

A generated 2-layer board: DP/DN pads on F.Cu facing each other across a GND plane on B.Cu whose polygon has a
rectangular bite (x 20..26, y 9..23) across the pair's straight path. The coupled section can dip below the bite
(y < 9) over solid plane at the price of a longer path. Exposure is measured geometrically here (samples of the
written tracks inside the bite): without --split-cost the pair runs straight through the bite; with
--split-cost 10 it detours under it, clipping at most the bite's bottom-left corner. (The pair search takes the
first legal goal, not the cost-minimal path, so a couple of corner samples are expected; the straight run's
exposure is two orders larger.) The summary's pair_void_samples audit field is checked alongside: 0 when the
split machinery is off, small on the detour.
"""
import json
import math
import pathlib
import re
import subprocess
import sys

HEAD = """(kicad_pcb (version 20240108) (generator "pcbnew")
  (general (thickness 1.6))
  (layers (0 "F.Cu" signal) (31 "B.Cu" signal) (44 "Edge.Cuts" user))
  (setup (pad_to_mask_clearance 0))
  (net 0 "") (net 1 "GND") (net 2 "DP") (net 3 "DN")
  (gr_rect (start 0 0) (end 40 24) (stroke (width 0.1) (type default)) (fill none) (layer "Edge.Cuts"))
"""


def pad(ref, x, y, net, name):
    return (f'  (footprint "T:P" (layer "F.Cu") (at {x} {y}) (property "Reference" "{ref}")\n'
            f'    (pad "1" smd rect (at 0 0) (size 1 0.3) (layers "F.Cu") (net {net} "{name}")))\n')


ZONE = ('  (zone (net 1) (net_name "GND") (layer "B.Cu") (uuid "zB") (hatch edge 0.5) (connect_pads yes (clearance 0.2))\n'
        '    (min_thickness 0.25) (fill yes (thermal_gap 0.5) (thermal_bridge_width 0.5))\n'
        '    (polygon (pts (xy 1 1) (xy 39 1) (xy 39 23) (xy 26 23) (xy 26 9) (xy 20 9) (xy 20 23) (xy 1 23))))\n')

BOARD = (HEAD + pad("J1", 4, 11.725, 2, "DP") + pad("J2", 4, 12.275, 3, "DN") +
         pad("J3", 36, 11.725, 2, "DP") + pad("J4", 36, 12.275, 3, "DN") + ZONE + ")\n")

SEG = re.compile(r"\(segment\s+\(start ([\d.]+) ([\d.]+)\)\s+\(end ([\d.]+) ([\d.]+)\)\s+\(width [\d.]+\)\s+\(layer \"F.Cu\"\)\s+\(net [23]\)")

errors = []


def check(cond, text):
    if not cond:
        errors.append(text)


def exposure(board_path):
    hits = 0
    for x0, y0, x1, y1 in (tuple(map(float, m)) for m in SEG.findall(board_path.read_text())):
        steps = max(1, int(math.hypot(x1 - x0, y1 - y0) / 0.1))
        for k in range(steps + 1):
            x, y = x0 + (x1 - x0) * k / steps, y0 + (y1 - y0) * k / steps
            if 20 < x < 26 and 9 < y < 23:
                hits += 1
    return hits


def route(tm, src, out, extra):
    js = pathlib.Path(str(out) + ".json")
    r = subprocess.run([str(tm), "route", str(src), "-o", str(out), "--json", str(js), "--diff-pairs",
                        "--critical-nets", "DP,DN", "--work", "2000000", "--variants", "1", "--threads", "1",
                        "--no-kb", "--no-gpu"] + extra, capture_output=True, text=True)
    if r.returncode not in (0, 3):
        sys.exit(f"{out.name}: tracemaker failed\n{r.stdout[-1500:]}\n{r.stderr[-1500:]}")
    return json.loads(js.read_text())


def main() -> int:
    tm, work = sys.argv[1], pathlib.Path(sys.argv[2])
    work.mkdir(parents=True, exist_ok=True)
    src = work / "pair_void.kicad_pcb"
    src.write_text(BOARD)
    plain_out, charged_out = work / "plain.kicad_pcb", work / "charged.kicad_pcb"
    plain = route(tm, src, plain_out, [])
    charged = route(tm, src, charged_out, ["--split-cost", "10"])
    for name, res in (("plain", plain), ("charged", charged)):
        check(res["routed"] == res["connections"], f"{name}: routed {res['routed']}/{res['connections']}")
        pairs = res.get("pairs", [])
        check(len(pairs) == 1 and pairs[0]["coupled_share"] >= 0.8, f"{name}: pair not coupled: {pairs}")
    pe, ce = exposure(plain_out), exposure(charged_out)
    check(pe >= 100, f"plain run should cross the bite, exposure {pe}")
    check(ce <= 12, f"charged run should detour under the bite, exposure {ce}")
    check(plain.get("pair_void_samples", -1) == 0, f"plain: audit off, pair_void_samples={plain.get('pair_void_samples')}")
    check(0 < charged.get("pair_void_samples", 99) <= 10, f"charged: audit small, pair_void_samples={charged.get('pair_void_samples')}")
    print(f"exposure: plain {pe}, charged {ce}; pair_void_samples: plain {plain.get('pair_void_samples')}, charged {charged.get('pair_void_samples')}")
    if errors:
        print("FAIL:", "; ".join(errors))
        return 1
    print("pair_void: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
