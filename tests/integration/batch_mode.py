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

"""Batch mode (issue #22): many boards, one process, one global thread pool.

Acceptance, as filed:
  - a batch of N boards produces N result JSONs identical in gate-relevant fields to
    N single-process runs under the same options and seeds (work-budgeted) -- here the
    output boards are byte-identical too;
  - total batch wall time on a multi-core host is less than the sequential sum, with
    the granted workers never exceeding the batch thread cap (the summary reports the
    peak it granted);
  - one malformed board yields an error result for that board and does not stop the
    rest; a board with a bad manifest option likewise, and a manifest with no jobs is
    a usage error (exit 2). Batch exit codes: 1 when a board failed, else 3 when a
    board left connections open, else 0.
"""
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

TM = sys.argv[1]
WORK = Path(sys.argv[2])
SRC = Path(__file__).resolve().parents[2] / "bench/data/freerouting/scripts/benchmark/fixtures/PCBench/4-port-usb-hub_4port-usb-hub/unrouted.kicad_pcb"
GATE = ("routed", "connections", "exit_code", "deterministic", "completion_pct")


def check(cond, msg):
    if not cond:
        raise SystemExit(f"FAIL: {msg}")


def run(args, timeout=900):
    t0 = time.time()
    p = subprocess.run([TM, *args], capture_output=True, text=True, timeout=timeout)
    return p, time.time() - t0


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    if not SRC.exists():
        print(f"SKIP: fixture missing: {SRC}")
        return 77
    WORK.mkdir(parents=True, exist_ok=True)
    (WORK / "corrupt.kicad_pcb").write_text("this is not a board\n")

    # the single-process reference (work-budgeted, seeded)
    p, single_wall = run(["route", str(SRC), "-o", str(WORK / "single.kicad_pcb"), "--json", str(WORK / "single.json"),
                          "--no-gpu", "--work", "300000", "--seed", "42"])
    check(p.returncode == 3, f"single: rc {p.returncode}")
    single = json.loads((WORK / "single.json").read_text())
    single_sha = sha(WORK / "single.kicad_pcb")

    def manifest(name, threads, jobs):
        mp = WORK / name
        mp.write_text(json.dumps({"threads": threads, "jobs": jobs}))
        return mp

    job = lambda out, **kw: {"input": str(SRC), "output": str(WORK / out), **kw}
    opts = {"options": {"seed": 42, "work": 300000}}

    # batch 1: two identical jobs + one corrupt board
    mp = manifest("m1.json", 24, [job("a.kicad_pcb", **opts), job("b.kicad_pcb", **opts),
                                  {"input": str(WORK / "corrupt.kicad_pcb"), "output": str(WORK / "c.kicad_pcb")}])
    p, batch_wall = run(["route-batch", str(mp), "--json", str(WORK / "batch1.json")])
    check(p.returncode == 1, f"batch1: rc {p.returncode} (a failed board must make it 1)")
    for n in ("a", "b"):
        j = json.loads((WORK / f"{n}.json").read_text())
        check(all(j.get(k) == single.get(k) for k in GATE), f"batch1 {n}: gate fields differ from the single run")
        check(sha(WORK / f"{n}.kicad_pcb") == single_sha, f"batch1 {n}: board differs from the single run")
    c = json.loads((WORK / "c.json").read_text())
    check(c.get("exit_code") == 1 and c.get("error"), f"batch1 corrupt: {c}")
    b = json.loads((WORK / "batch1.json").read_text())
    check(b["batch"]["boards_failed"] == 1 and b["batch"]["boards_partial"] == 2, f"batch1 summary: {b['batch']}")
    check(b["batch"]["peak_workers_granted"] <= 24, f"batch1: granted {b['batch']['peak_workers_granted']} over the cap")
    check([j["exit_code"] for j in b["jobs"]] == [3, 3, 1], f"batch1 job order/codes: {b['jobs']}")
    check(batch_wall < 0.85 * 2 * single_wall + 2.0, f"batch1 wall {batch_wall:.1f}s not below the sequential sum {2 * single_wall:.1f}s")

    # batch 2: no failures, opens remain -> exit 3
    mp = manifest("m2.json", 24, [job("a2.kicad_pcb", **opts), job("b2.kicad_pcb", **opts)])
    p, _ = run(["route-batch", str(mp), "--json", str(WORK / "batch2.json")])
    check(p.returncode == 3, f"batch2: rc {p.returncode} != 3")

    # batch 6: peak RSS is reported once, on the batch; job rows carry the process peak under its own name
    b2 = json.loads((WORK / "batch2.json").read_text())
    check("peak_rss_mb" in b2["batch"], f"batch6: batch peak missing: {b2}")
    check(all("process_peak_rss_mb" in j and "peak_rss_mb" not in j for j in b2["jobs"]), f"batch6: job rows: {b2}")
    check(b2["batch"]["peak_rss_mb"] >= max(j["process_peak_rss_mb"] for j in b2["jobs"]), "batch6: batch peak below a job row")

    # batch 3: per-board manifest errors are isolated; a jobless manifest is a usage error
    mp = manifest("m3.json", 8, [job("d.kicad_pcb", options={"sed": 42}),
                                 job("e.kicad_pcb", options={"threads": 4}),
                                 job("f.kicad_pcb", **opts)])
    p, _ = run(["route-batch", str(mp), "--json", str(WORK / "batch3.json")])
    check(p.returncode == 1, f"batch3: rc {p.returncode} != 1")
    d = json.loads((WORK / "d.json").read_text())
    check("unknown option 'sed'" in (d.get("error") or ""), f"batch3 d: {d.get('error')}")
    e = json.loads((WORK / "e.json").read_text())
    check("threads" in (e.get("error") or ""), f"batch3 e: {e.get('error')}")
    f = json.loads((WORK / "f.json").read_text())
    check(all(f.get(k) == single.get(k) for k in GATE), "batch3 f: the good board was disturbed by its neighbours")
    mp = WORK / "m4.json"
    mp.write_text(json.dumps({"jobs": []}))
    p, _ = run(["route-batch", str(mp)])
    check(p.returncode == 2, f"batch3 empty manifest: rc {p.returncode} != 2")
    # batch 4: manifest values are validated per board, like the CLI validates flags
    mp = manifest("m5.json", 8, [job("g.kicad_pcb", options={"repair": "bogus"}),
                                 job("h.kicad_pcb", options={"work": -5}),
                                 {"input": str(SRC), "output": ""}])
    p, _ = run(["route-batch", str(mp), "--json", str(WORK / "batch4.json")])
    check(p.returncode == 1, f"batch4: rc {p.returncode} != 1")
    g = json.loads((WORK / "g.json").read_text())
    check("repair" in (g.get("error") or ""), f"batch4 g: {g}")
    h = json.loads((WORK / "h.json").read_text())
    check("work" in (h.get("error") or ""), f"batch4 h: {h}")
    ij = json.loads((WORK / "batch4.json").read_text())
    errs = [j.get("error") or "" for j in ij["jobs"]]
    check(any("non-empty" in e for e in errs), f"batch4 empty output: {errs}")
    mp = manifest("m6.json", -2, [job("z.kicad_pcb", **opts)])
    p, _ = run(["route-batch", str(mp)])
    check(p.returncode == 2, f"batch4 negative threads: rc {p.returncode} != 2")

    # batch 5: no_gpu is a batch option (the batch resolves the GPU device like a single run)
    mp = manifest("m7.json", 8, [job("n.kicad_pcb", options={"seed": 42, "work": 300000, "no_gpu": True})])
    p, _ = run(["route-batch", str(mp), "--json", str(WORK / "batch5.json")])
    check(p.returncode == 3, f"batch5: rc {p.returncode} != 3")
    n = json.loads((WORK / "n.json").read_text())
    check(all(n.get(k) == single.get(k) for k in GATE), "batch5: no_gpu board differs from the single run")

    # batch 7: a negative --threads override is a usage error even when the manifest sets threads
    mp = manifest("m8.json", 8, [job("y.kicad_pcb", **opts)])
    p, _ = run(["route-batch", str(mp), "--threads=-2"])
    check(p.returncode == 2, f"batch7: rc {p.returncode} != 2")

    print("PASS batch_mode")
    return 0


if __name__ == "__main__":
    sys.exit(main())
