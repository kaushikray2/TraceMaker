#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""--deterministic mode (issue #17): the deterministic contract as one switch.

  deterministic_mode.py <tracemaker> <work dir>

On the usb-hub fixture with the default knowledge-base path live under an isolated HOME:
  A) --deterministic --work 1000000 at --threads 1 and 8, no --seed typed: byte-identical boards,
     deterministic true, deterministic_mode true, kb_used false (the mode isolates the run from the
     default kb without --no-kb), the reported seed is the fixed default 1.
  B) --deterministic --seed 42 --work 1000000: deterministic true, reported seed 42.
  C) --deterministic --time 60 with no work budget: refused (nonzero exit, the error names the mode).
  D) --deterministic --work 1000000 --halving: refused (halving sizes rungs by the thread count).
  E) --deterministic --work 20000000 --time 1: the safety net binds; the run reports
     deterministic false with a deterministic_violation naming the time limit.
  F) --deterministic --work 1000000 --kb FILE: the explicit --kb is honoured and reported as the
     violation (kb_used true, deterministic false, violation names the knowledge base).
  G) --deterministic --round-work 20000 --rounds 1 at --threads 1 and 8 (no --work): identical boards,
     deterministic true -- the variant set must not scale with --threads for a round-work budget.
  H) --deterministic --relax --work 1000000: refused -- relax rounds are bounded by --round-work /
     --rounds, not --work, so the wall clock would bind them.
Exit 77 (skipped) when the fixture is missing.
"""
import json
import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
FIX = ROOT / "bench/data/freerouting/scripts/benchmark/fixtures/PCBench"
SRC = FIX / "4-port-usb-hub_4port-usb-hub/unrouted.kicad_pcb"


def check(cond, msg):
    if not cond:
        raise SystemExit(f"FAIL: {msg}")


def route(tm, home, cwd, out, js, *extra, expect_fail=False):
    env = dict(os.environ, HOME=str(home))
    env.pop("XDG_DATA_HOME", None)  # the kb default path must land under the scenario HOME
    p = subprocess.run([str(tm), "route", str(SRC), "-o", str(out), "--json", str(js), "--no-gpu", *extra],
                       capture_output=True, text=True, cwd=cwd, env=env)
    if expect_fail:
        check(p.returncode not in (0, 3), f"expected refusal, got exit {p.returncode}: {p.stderr[-500:]}")
        return p
    if p.returncode not in (0, 3) or not out.exists() or not js.exists():
        print(p.stdout[-2000:], p.stderr[-2000:])
        raise SystemExit(f"FAIL: route exited {p.returncode}")
    return out.read_bytes(), json.loads(js.read_text())


def main():
    tm, work = sys.argv[1], pathlib.Path(sys.argv[2])
    if not SRC.exists():
        print(f"fixture missing: {SRC}")
        return 77
    home, cwd = work / "home", work / "cwd"
    home.mkdir(parents=True, exist_ok=True)
    cwd.mkdir(parents=True, exist_ok=True)

    boards = []
    for tag, threads in (("t1", 1), ("t8", 8)):
        data, s = route(tm, home, cwd, cwd / f"a-{tag}.kicad_pcb", cwd / f"a-{tag}.json",
                        "--deterministic", "--work", "1000000", "--threads", str(threads))
        check(s.get("deterministic") is True, f"A/{tag}: deterministic is not true: {s.get('deterministic')}")
        check(s.get("deterministic_mode") is True, f"A/{tag}: deterministic_mode missing")
        check("deterministic_violation" not in s, f"A/{tag}: unexpected violation: {s.get('deterministic_violation')}")
        check(s.get("kb_used") is False, f"A/{tag}: kb_used is not false under --deterministic: {s.get('kb_used')}")
        check(s.get("run", {}).get("seed") == 1, f"A/{tag}: default seed is not the fixed 1: {s.get('run')}")
        boards.append(data)
        print(f"A threads {threads}: routed {s['routed']}/{s['connections']}, {len(data)} bytes")
    check(boards[0] == boards[1], "A: boards differ across thread counts under --deterministic")

    _, s = route(tm, home, cwd, cwd / "b.kicad_pcb", cwd / "b.json",
                 "--deterministic", "--seed", "42", "--work", "1000000", "--threads", "8")
    check(s.get("deterministic") is True, "B: deterministic is not true with an explicit --seed")
    check(s.get("run", {}).get("seed") == 42, f"B: reported seed is not 42: {s.get('run')}")
    print("B: explicit --seed 42 honoured")

    p = route(tm, home, cwd, cwd / "c.kicad_pcb", cwd / "c.json", "--deterministic", "--time", "60", expect_fail=True)
    check("--deterministic" in p.stderr, f"C: refusal does not name the mode: {p.stderr[-300:]}")
    print("C: --time without a work budget refused")

    p = route(tm, home, cwd, cwd / "d.kicad_pcb", cwd / "d.json",
              "--deterministic", "--work", "1000000", "--halving", expect_fail=True)
    check("halving" in p.stderr, f"D: refusal does not name halving: {p.stderr[-300:]}")
    print("D: --halving refused")

    _, s = route(tm, home, cwd, cwd / "e.kicad_pcb", cwd / "e.json",
                 "--deterministic", "--work", "20000000", "--time", "1", "--threads", "8")
    check(s.get("deterministic") is False, "E: deterministic is not false after the safety net bound")
    check("time limit" in str(s.get("deterministic_violation", "")),
          f"E: violation does not name the time limit: {s.get('deterministic_violation')}")
    print(f"E: safety-net violation reported: {s.get('deterministic_violation')}")

    _, s = route(tm, home, cwd, cwd / "f.kicad_pcb", cwd / "f.json",
                 "--deterministic", "--work", "1000000", "--kb", str(cwd / "kb.sqlite"), "--threads", "8")
    check(s.get("kb_used") is True, "F: kb_used is not true with an explicit --kb")
    check(s.get("deterministic") is False, "F: deterministic is not false with the kb in use")
    check("knowledge base" in str(s.get("deterministic_violation", "")),
          f"F: violation does not name the knowledge base: {s.get('deterministic_violation')}")
    print(f"F: --kb violation reported: {s.get('deterministic_violation')}")

    boards = []
    for tag, threads in (("t1", 1), ("t8", 8)):
        data, s = route(tm, home, cwd, cwd / f"g-{tag}.kicad_pcb", cwd / f"g-{tag}.json",
                        "--deterministic", "--round-work", "20000", "--rounds", "1", "--threads", str(threads))
        check(s.get("deterministic") is True, f"G/{tag}: deterministic not true with --round-work only")
        boards.append(data)
        print(f"G threads {threads}: routed {s.get('routed')}/{s.get('connections')}, {len(data)} bytes")
    check(boards[0] == boards[1], "G: boards differ across thread counts under --deterministic --round-work")

    p = route(tm, home, cwd, cwd / "h.kicad_pcb", cwd / "h.json",
              "--deterministic", "--relax", "--work", "1000000", expect_fail=True)
    check("--deterministic" in p.stderr, f"H: refusal does not name the mode: {p.stderr[-300:]}")
    print("H: --relax with --work only refused (relax rounds are not bounded by --work)")

    print("deterministic_mode: all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
