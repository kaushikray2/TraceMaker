# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SiliconBrane Inc.
"""Issue 39: --escape-release-open gives back the corridors of pads no routed connection used.

On the 4-port USB hub fixture the escape plan reserves 25 corridors and at least one pad's
connection stays open through the first pass, so the release must fire exactly there:
- without the flag, escape_released_open stays 0 (the corridors stand for the whole run);
- with the flag, escape_released_open >= 1, the run is deterministic (two runs byte-identical),
  and the released run leaves no more connections open than the standing-corridor run.

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


def route(tm, work, tag, *extra):
    js = work / f"{tag}.json"
    out = work / f"{tag}.kicad_pcb"
    p = subprocess.run([str(tm), "route", str(SRC), "-o", str(out), "--json", str(js), "--no-gpu",
                        "--deterministic", "--work", "20000000", "--escape-plan", *extra],
                       capture_output=True, text=True)
    check(p.returncode in (0, 3), f"{tag}: route rc {p.returncode}: {p.stdout[-300:]} {p.stderr[-200:]}")
    return out, json.loads(js.read_text())


def main():
    tm, work = sys.argv[1], pathlib.Path(sys.argv[2])
    if not SRC.exists():
        print(f"fixture missing: {SRC}")
        return 77
    work.mkdir(parents=True, exist_ok=True)

    _, base = route(tm, work, "held")
    check(base.get("escape_corridors", 0) > 0, f"held: no corridors planned ({base.get('escape_corridors')})")
    check(base.get("escape_released_open", -1) == 0,
          f"held: corridors released without the flag ({base.get('escape_released_open')})")
    base_open = base["connections"] - base["routed"]

    outs = []
    for tag in ("rel1", "rel2"):
        out, s = route(tm, work, tag, "--escape-release-open")
        outs.append((out, s))
        check(s.get("escape_released_open", 0) >= 1,
              f"{tag}: the release never fired ({s.get('escape_released_open')})")
        check(s["connections"] - s["routed"] <= base_open,
              f"{tag}: released run left more open ({s['connections'] - s['routed']}) than the held run ({base_open})")
    h = [hashlib.sha256(o.read_bytes()).hexdigest() for o, _ in outs]
    check(h[0] == h[1], "release runs differ: the release is not deterministic")
    print(f"PASS escape_release: corridors {base['escape_corridors']}, "
          f"released {outs[0][1]['escape_released_open']}, open held {base_open} -> released "
          f"{outs[0][1]['connections'] - outs[0][1]['routed']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
