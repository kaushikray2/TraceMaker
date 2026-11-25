#!/usr/bin/env python3
"""Bystander-safe scoped reroute (Tier 1): --reroute-net / --reroute-window.

The plugin's re-route stage was disabled because the engine's --reroute strips every
unlocked track and via on the board, splitting nets the re-route was never about. The
scoped forms promise: (a) nets outside the scope keep every track and via, byte for
byte; (b) in-scope copper that stays (locked copper, and window-mode copper outside
the window) is the fixed anchor the re-route connects to; (c) the route JSON reports
exactly which nets were re-routed and how much copper was ripped.

Scenario on the usb-hub fixture: a cheap route plus the --route-open-only finisher
makes a completed board F. Then:
  net arm:    --reroute-net D2- reconnects D2- (rc 0, routed == connections) with
              every other net's copper identical to F, and D2-'s own copper changed.
  window arm: a window round one D2- pad (pad positions read from F's footprints)
              reports D2- in its scope, completes, and every net outside the REPORTED
              scope is identical to F.
  refusals:   scoped + --reroute, a malformed window, a pattern matching nothing,
              and a window covering no pad all exit 1.
"""
import json
import math
import re
import subprocess
import sys
from pathlib import Path

TM = sys.argv[1]
WORK = Path(sys.argv[2])
SRC = Path(__file__).resolve().parents[2] / "bench/data/freerouting/scripts/benchmark/fixtures/PCBench/4-port-usb-hub_4port-usb-hub/unrouted.kicad_pcb"


def check(cond, msg):
    if not cond:
        raise SystemExit(f"FAIL: {msg}")


def route(*args):
    return subprocess.run([TM, "route", *args], capture_output=True, text=True, timeout=1200)


def blocks(text, kw):
    out, i = [], 0
    while True:
        j = text.find("(" + kw, i)
        if j < 0:
            return out
        depth, k = 0, j
        while k < len(text):
            if text[k] == "(":
                depth += 1
            elif text[k] == ")":
                depth -= 1
                if depth == 0:
                    break
            k += 1
        out.append(text[j:k + 1])
        i = k + 1


def net_names(text):
    nets = {}
    for m in re.finditer(r'[(]net (\d+) (?:"([^"]*)"|([^\s)]+))', text):
        nets[int(m.group(1))] = m.group(2) if m.group(2) is not None else m.group(3)
    return nets


def copper(path):
    """net name -> set of normalised (segment|via) block texts, uuids stripped."""
    text = path.read_text()
    nets = net_names(text)
    items = {}
    for kw in ("segment", "via"):
        for b in blocks(text, kw):
            if b.startswith(("(segment_width", "(via_size", "(via_drill")):
                continue
            m = re.search(r"[(]net (\d+)[)]", b)
            name = nets.get(int(m.group(1)), "?") if m else "?"
            key = re.sub(r"[(](uuid|tstamp) [^)]*[)]", "", b)
            key = re.sub(r"\s+", " ", key).strip()
            items.setdefault(name, set()).add(key)
    return items


def pad_positions(path, net_name):
    """Absolute pad positions of one net, from the footprint transforms in the file."""
    text = path.read_text()
    nets = net_names(text)
    pts = []
    for mod in blocks(text, "module") + blocks(text, "footprint"):
        ma = re.search(r"[(]at ([\d.-]+) ([\d.-]+)(?: ([\d.-]+))?[)]", mod)
        if not ma:
            continue
        mx, my = float(ma.group(1)), float(ma.group(2))
        th = math.radians(float(ma.group(3)) if ma.group(3) else 0.0)
        for pad in blocks(mod, "pad"):
            pa = re.search(r"[(]at ([\d.-]+) ([\d.-]+)", pad)
            nm = re.search(r"[(]net (\d+)", pad)
            if not pa or not nm or nets.get(int(nm.group(1))) != net_name:
                continue
            px, py = float(pa.group(1)), float(pa.group(2))
            # KiCad convention (y axis down): x' = x cos + y sin ; y' = -x sin + y cos
            pts.append((mx + px * math.cos(th) + py * math.sin(th), my - px * math.sin(th) + py * math.cos(th)))
    return pts


def main():
    if not SRC.exists():
        print(f"SKIP: fixture missing: {SRC}")
        return 77
    WORK.mkdir(parents=True, exist_ok=True)
    partial, pj = WORK / "partial.kicad_pcb", WORK / "partial.json"
    p = route(str(SRC), "-o", str(partial), "--json", str(pj), "--no-gpu", "--work", "300000", "--seed", "42")
    check(p.returncode == 3, f"setup route: rc {p.returncode}")
    full, fj = WORK / "full.kicad_pcb", WORK / "full.json"
    p = route(str(partial), "-o", str(full), "--json", str(fj), "--no-gpu", "--route-open-only", "--work", "20000000", "--seed", "42")
    check(p.returncode == 0, f"setup finisher: rc {p.returncode}")
    base = copper(full)
    check(len(base.get("D2-", ())) >= 5, "setup: D2- should carry copper on the completed board")

    # ---- net arm ----
    out, oj = WORK / "net.kicad_pcb", WORK / "net.json"
    p = route(str(full), "-o", str(out), "--json", str(oj), "--no-gpu", "--reroute-net", "D2-", "--work", "20000000", "--seed", "42")
    check(p.returncode == 0, f"net arm: rc {p.returncode}: {p.stderr[-300:]}")
    s = json.loads(oj.read_text())
    rr = s.get("rerouted") or {}
    check(rr.get("nets") == ["D2-"], f"net arm: rerouted nets {rr.get('nets')}")
    check(rr.get("ripped_tracks", 0) + rr.get("ripped_vias", 0) > 0, f"net arm: nothing ripped: {rr}")
    check(s.get("routed") == s.get("connections"), f"net arm: {s.get('routed')}/{s.get('connections')} routed")
    after = copper(out)
    for name in set(base) | set(after):
        if name == "D2-":
            continue
        check(base.get(name, set()) == after.get(name, set()), f"net arm: bystander net {name} changed")
    check(base.get("D2-") != after.get("D2-"), "net arm: D2- copper unchanged -- the rip did not happen")

    # ---- window arm ----
    pts = pad_positions(full, "D2-")
    check(len(pts) >= 2, f"window arm: expected >= 2 D2- pads, got {len(pts)}")
    x, y = pts[0]
    win = f"{x - 1.0:.3f},{y - 1.0:.3f},{x + 1.0:.3f},{y + 1.0:.3f}"
    out, oj = WORK / "win.kicad_pcb", WORK / "win.json"
    p = route(str(full), "-o", str(out), "--json", str(oj), "--no-gpu", "--reroute-window", win, "--work", "20000000", "--seed", "42")
    check(p.returncode == 0, f"window arm: rc {p.returncode}: {p.stderr[-300:]}")
    s = json.loads(oj.read_text())
    rr = s.get("rerouted") or {}
    check("D2-" in (rr.get("nets") or []), f"window arm: D2- not in reported scope {rr.get('nets')}")
    check("window_mm" in rr, "window arm: window_mm missing from the report")
    check(s.get("routed") == s.get("connections"), f"window arm: {s.get('routed')}/{s.get('connections')} routed")
    scope = set(rr.get("nets") or [])
    after = copper(out)
    for name in set(base) | set(after):
        if name in scope:
            continue
        check(base.get(name, set()) == after.get(name, set()), f"window arm: out-of-scope net {name} changed")

    # ---- layers arm: scoped reroute combined with --copper-layers ----
    # The layer-count edit re-parses the board from the document mid-job; the scoped
    # locks live only in the model, so a reparse that drops them lets the route rip
    # bystander copper. Bystanders must still be byte-identical to F.
    cu = sorted(set(re.findall("[A-Za-z0-9_.]+[.]Cu", full.read_text())))
    target = len(cu) + 2 + (len(cu) % 2)  # layer counts are even; the token count can over-read by one
    out, oj = WORK / "layers.kicad_pcb", WORK / "layers.json"
    p = route(str(full), "-o", str(out), "--json", str(oj), "--no-gpu", "--reroute-net", "D2-",
              "--copper-layers", str(target), "--work", "20000000", "--seed", "42")
    check(p.returncode == 0, f"layers arm: rc {p.returncode}: {p.stderr[-300:]}")
    s = json.loads(oj.read_text())
    check(s.get("routed") == s.get("connections"), "layers arm: not all connections routed")
    after = copper(out)
    for name in set(base) | set(after):
        if name == "D2-":
            continue
        check(base.get(name, set()) == after.get(name, set()), f"layers arm: bystander net {name} changed")
    check(base.get("D2-") != after.get("D2-"), "layers arm: D2- copper unchanged")
    # ---- refusals ----
    p = route(str(full), "-o", str(WORK / "x.kicad_pcb"), "--no-gpu", "--reroute-net", "D2-", "--reroute")
    check(p.returncode == 1, f"refusal reroute+scoped: rc {p.returncode}")
    p = route(str(full), "-o", str(WORK / "x.kicad_pcb"), "--no-gpu", "--reroute-window", "1,2,3")
    check(p.returncode == 1, f"refusal malformed window: rc {p.returncode}")
    p = route(str(full), "-o", str(WORK / "x.kicad_pcb"), "--no-gpu", "--reroute-window", win + ",")
    check(p.returncode == 1, f"refusal trailing-comma window: rc {p.returncode}")
    p = route(str(full), "-o", str(WORK / "x.kicad_pcb"), "--no-gpu", "--reroute-window", "nan,0,1,1")
    check(p.returncode == 1, f"refusal nan window: rc {p.returncode}")
    p = route(str(full), "-o", str(WORK / "x.kicad_pcb"), "--no-gpu", "--reroute-net", "NOPE*")
    check(p.returncode == 1, f"refusal empty net scope: rc {p.returncode}")
    p = route(str(full), "-o", str(WORK / "x.kicad_pcb"), "--no-gpu", "--reroute-window", "0,0,1,1")
    check(p.returncode == 1, f"refusal empty window: rc {p.returncode}")
    print("PASS reroute_scope")
    return 0


if __name__ == "__main__":
    sys.exit(main())
