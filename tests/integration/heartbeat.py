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

# SPDX-License-Identifier: GPL-3.0-or-later
"""Progress heartbeat (Tier 1): --heartbeat FILE rewritten while the job runs.

  heartbeat.py <tracemaker> <work dir>

Routes the usb-hub fixture slowly enough to observe (--threads 2, --work 20000000) with
--heartbeat-s 1 and polls the file while the process runs: it must appear, its elapsed_s must
advance across samples, and at least one mid-run sample must carry stage/routed/open. After the
process exits, the file must hold the final state: done true, and routed/open equal to the route
JSON's own counts. Exit 77 (skipped) when the fixture is missing.
"""
import json
import pathlib
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
FIX = ROOT / "bench/data/freerouting/scripts/benchmark/fixtures/PCBench"
SRC = FIX / "4-port-usb-hub_4port-usb-hub/unrouted.kicad_pcb"


def check(cond, msg):
    if not cond:
        raise SystemExit(f"FAIL: {msg}")


def main():
    tm, work = sys.argv[1], pathlib.Path(sys.argv[2])
    if not SRC.exists():
        print(f"fixture missing: {SRC}")
        return 77
    work.mkdir(parents=True, exist_ok=True)
    hb, js, out = work / "hb.json", work / "sum.json", work / "out.kicad_pcb"
    p = subprocess.Popen([str(tm), "route", str(SRC), "-o", str(out), "--json", str(js), "--no-gpu",
                          "--work", "20000000", "--threads", "2",
                          "--heartbeat", str(hb), "--heartbeat-s", "1"],
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    elapsed_seen, saw_progress = [], False
    while p.poll() is None:
        if hb.exists():
            try:
                j = json.loads(hb.read_text())
            except (json.JSONDecodeError, OSError):
                j = None  # a reader may catch the rename mid-flight on some filesystems; retry next poll
            if j is not None:
                if "elapsed_s" in j:
                    elapsed_seen.append(j["elapsed_s"])
                if "routed" in j and "open" in j and "stage" in j:
                    saw_progress = True
        time.sleep(0.5)
    rc = p.wait()
    check(rc in (0, 3), f"route exited {rc}: {p.stdout.read()[-1000:]}")
    distinct = sorted(set(round(e) for e in elapsed_seen))
    check(len(distinct) >= 3, f"heartbeat did not advance while running: {distinct}")
    check(saw_progress, "no mid-run heartbeat sample carried stage/routed/open")
    final = json.loads(hb.read_text())
    s = json.loads(js.read_text())
    check(final.get("done") is True, f"final heartbeat is not marked done: {final}")
    check(final.get("routed") == s["routed"], f"final routed {final.get('routed')} != summary {s['routed']}")
    check(final.get("open") == s["connections"] - s["routed"],
          f"final open {final.get('open')} != summary open {s['connections'] - s['routed']}")
    print(f"heartbeat: {len(distinct)} distinct elapsed seconds mid-run, final routed {final['routed']}/{final['connections']}")
    print("heartbeat: all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
