#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Deterministic runs under an explicit --seed (Stage 2A gate; the AI Router plugin's Tier 1 ask).

  seed_determinism.py <tracemaker> <work dir>

Routes a PCBench board with the plugin's flag mix (--work, --seed, --advice, --soft-zones,
--keep-vias-off-pads, --diff-pairs, --si-rules, --critical-auto; --no-gpu added because GPU/CPU field
equality is a separate gate) and NO --kb/--no-kb, at --threads 1, 4 and 8 plus a repeat, on an unrouted
board and on a partially routed one the same mix produced (repair active). Every run of a board must write
a byte-identical .kicad_pcb, and its route.json must promise the run was deterministic: kb_used false (an
explicit --seed isolates the run from the default kb.sqlite: it is neither read nor written),
deterministic true, time_limited false. A control pair without --seed must still use the knowledge base
(backwards compatibility for interactive runs). Exit 77 (skipped) when the fixture is missing.
"""
import json
import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
FIX = ROOT / "bench/data/freerouting/scripts/benchmark/fixtures/PCBench"
SRC = FIX / "4-port-usb-hub_4port-usb-hub/unrouted.kicad_pcb"
MIX = ["--seed", "42", "--soft-zones", "--keep-vias-off-pads", "--diff-pairs", "--si-rules", "--critical-auto", "--no-gpu"]


def route(tm, home, cwd, board, out, js, *extra):
    env = dict(os.environ, HOME=str(home))
    env.pop("XDG_DATA_HOME", None)  # the kb default path must land under the scenario HOME
    p = subprocess.run([str(tm), "route", str(board), "-o", str(out), "--json", str(js), *extra],
                       capture_output=True, text=True, cwd=cwd, env=env)
    if p.returncode not in (0, 3) or not out.exists() or not js.exists():
        print(p.stdout[-2000:], p.stderr[-2000:])
        raise SystemExit(f"FAIL: route exited {p.returncode}")
    return out.read_bytes(), json.loads(js.read_text())


def check(cond, msg):
    if not cond:
        raise SystemExit(f"FAIL: {msg}")


def seeded_arms(tm, work, board, advice, label, expect_repair):
    home, cwd = work / f"{label}-home", work / f"{label}-cwd"
    home.mkdir(parents=True, exist_ok=True)
    cwd.mkdir(parents=True, exist_ok=True)
    seen = []
    for tag, threads in (("t1", 1), ("t4", 4), ("t8", 8), ("t8b", 8)):
        data, s = route(tm, home, cwd, board, cwd / f"{tag}.kicad_pcb", cwd / f"{tag}.json",
                        "--work", "1000000", "--advice", str(advice), "--threads", str(threads), *MIX)
        check(s.get("kb_used") is False, f"{label}/{tag}: kb_used is not false under --seed: {s.get('kb_used')}")
        check(s.get("deterministic") is True, f"{label}/{tag}: deterministic is not true: {s.get('deterministic')}")
        check(s.get("time_limited") is False, f"{label}/{tag}: time_limited is not false")
        if expect_repair and s.get("open", 0) > 0:
            check("repair" in s and s["repair"].get("attempts", 0) >= 1,
                  f"{label}/{tag}: connections left open but repair did not run")
        seen.append(data)
        print(f"{label} threads {threads} ({tag}): routed {s['routed']}/{s['connections']}, {len(data)} bytes")
    check(all(d == seen[0] for d in seen), f"{label}: output boards differ across threads/repeats")
    kb_files = [p for p in home.rglob("*.sqlite*")]
    check(not kb_files, f"{label}: a knowledge base file appeared under the seeded HOME: {kb_files}")
    print(f"{label}: PASS (byte-identical at --threads 1, 4, 8 and on repeat; no kb.sqlite created)")


def main() -> int:
    tm, work = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
    if not SRC.exists():
        print(f"skip: {SRC} missing (scripts/fetch_fixtures.sh)")
        return 77
    work.mkdir(parents=True, exist_ok=True)
    scratch = work / "scratch"
    scratch.mkdir(exist_ok=True)
    # An advice file naming a net this board really leaves open (advice v1 is strict: a made-up name is refused).
    # The probe budget is not the point of the test, so shrink it until something is left open.
    probe = {}
    for budget in ("100000", "10000", "1000"):
        _, probe = route(tm, scratch, scratch, SRC, scratch / "probe.kicad_pcb", scratch / "probe.json",
                         "--work", budget, "--variants", "1", "--no-kb", "--no-gpu")
        if probe.get("failures"):
            break
    check(probe.get("failures"), "probe run left nothing unrouted: cannot build the advice file")
    advice = work / "advice.json"
    # The summary's failures list names each open connection as "NET: pad -> pad (why)"; advise its net first.
    advice.write_text(json.dumps({"version": 1, "first_nets": [probe["failures"][0].split(": ", 1)[0]]}))
    # Board 1: the unrouted board. Board 2: a partially routed one the same mix produced (repair active).
    seeded_arms(tm, work, SRC, advice, "unrouted", False)
    gen_home, gen_cwd = work / "gen-home", work / "gen-cwd"
    gen_home.mkdir(exist_ok=True)
    gen_cwd.mkdir(exist_ok=True)
    partial = gen_cwd / "partial.kicad_pcb"
    gen = {}
    for budget in ("150000", "50000", "15000"):
        _, gen = route(tm, gen_home, gen_cwd, SRC, partial, gen_cwd / "gen.json",
                       "--work", budget, "--advice", str(advice), *MIX)
        if 0 < gen["routed"] < gen["connections"]:
            break
    check(0 < gen["routed"] < gen["connections"], f"partial board is not partial: {gen['routed']}/{gen['connections']} routed")
    print(f"partial board: {gen['routed']}/{gen['connections']} routed")
    # Repair engages on a board that already carries copper (route_job: repair runs when the job asks for it or
    # the input has copper to lift). A small-budget run over the partial board must show it.
    _, pin = route(tm, gen_home, gen_cwd, partial, gen_cwd / "pin.kicad_pcb", gen_cwd / "pin.json",
                   "--work", "1000", "--advice", str(advice), *MIX)
    check("repair" in pin and pin["repair"].get("attempts", 0) >= 1,
          "repair did not engage on the partially routed board")
    print(f"repair pin: attempts {pin['repair']['attempts']} on the partially routed board")
    seeded_arms(tm, work, partial, advice, "partial", True)
    # Control: without --seed the knowledge base is still used (interactive backwards compatibility).
    home, cwd = work / "kb-home", work / "kb-cwd"
    home.mkdir(exist_ok=True)
    cwd.mkdir(exist_ok=True)
    for tag in ("r1", "r2"):
        _, s = route(tm, home, cwd, SRC, cwd / f"{tag}.kicad_pcb", cwd / f"{tag}.json",
                     "--work", "200000", "--no-gpu")
        check(s.get("kb_used") is True, f"kb control {tag}: kb_used is not true without --seed")
        check(s.get("deterministic") is False, f"kb control {tag}: deterministic claimed without --seed")
    check(any(home.rglob("kb.sqlite")), "kb control: no kb.sqlite was written")
    print("kb control: PASS (knowledge base used and written when --seed is not given)")
    # The record_replay shape: no --seed either, but --no-kb with a work budget. The seed defaults to a fixed 1,
    # so the run is inside the deterministic contract and must say so.
    home2, cwd2 = work / "nokb-home", work / "nokb-cwd"
    home2.mkdir(exist_ok=True)
    cwd2.mkdir(exist_ok=True)
    _, s = route(tm, home2, cwd2, SRC, cwd2 / "nokb.kicad_pcb", cwd2 / "nokb.json",
                 "--work", "200000", "--no-gpu", "--no-kb")
    check(s.get("kb_used") is False, "no-kb control: kb_used is not false")
    check(s.get("deterministic") is True, "no-kb control: a --work --no-kb run is not reported deterministic")
    check(s.get("time_limited") is False, "no-kb control: unexpectedly time limited")
    check(not any(home2.rglob("kb.sqlite")), "no-kb control: a kb.sqlite was written")
    print("no-kb control: PASS (--work --no-kb reports deterministic)")
    print("PASS: seeded runs are byte-identical across threads and repeats, on both boards")
    return 0


if __name__ == "__main__":
    sys.exit(main())
